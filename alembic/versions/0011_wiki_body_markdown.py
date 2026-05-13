"""switch wiki_pages.content (BlockNote JSONB) → wiki_pages.body (markdown TEXT)

Revision ID: 0011_wiki_body_markdown
Revises: 0010_wikis_layer
Create Date: 2026-05-13

The wiki editor moves from BlockNote (block-JSON model) to Milkdown
(Typora-style markdown WYSIWYG). Storing markdown directly:

* puts the wiki on the same data shape as chat messages, so the same
  ``<Markdown>`` renderer can be reused;
* makes RAG ingestion trivial — chunk the body string, no JSON walk;
* drops a dependency on BlockNote's internal block schema.

This migration adds a ``body`` TEXT column, transcodes every existing
``content`` JSON tree into markdown, and drops the old column. The
transcoder is intentionally lossy on BlockNote-specific block types
that have no clean markdown equivalent (images, video, file embeds,
toggle blocks) — those become a placeholder ``> [block type]`` line so
the content isn't silently dropped.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0011_wiki_body_markdown"
down_revision: str | None = "0010_wikis_layer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _inline_text(content: Any) -> str:
    """Flatten a BlockNote inline-content array to markdown.

    BlockNote inline nodes:
      - ``text``  with optional ``styles`` ({bold, italic, code, …})
      - ``link``  with ``href`` + nested ``content``
    Anything else falls through as best-effort text.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        t = item.get("type")
        if t == "text":
            txt = item.get("text", "")
            styles = item.get("styles") or {}
            if styles.get("code"):
                txt = f"`{txt}`"
            if styles.get("bold"):
                txt = f"**{txt}**"
            if styles.get("italic"):
                txt = f"*{txt}*"
            if styles.get("strike") or styles.get("strikethrough"):
                txt = f"~~{txt}~~"
            parts.append(txt)
        elif t == "link":
            inner = _inline_text(item.get("content"))
            href = item.get("href", "")
            parts.append(f"[{inner}]({href})")
        else:
            # Unknown inline — fall back to nested content if any.
            parts.append(_inline_text(item.get("content")))
    return "".join(parts)


def _block_to_markdown(block: dict[str, Any]) -> str | None:
    """Render a single BlockNote block as a markdown paragraph.

    Returns ``None`` for blocks that should be skipped (eg. empty
    paragraphs at the document tail).
    """
    if not isinstance(block, dict):
        return None
    t = block.get("type", "paragraph")
    props = block.get("props") or {}
    text = _inline_text(block.get("content"))

    if t == "heading":
        level = int(props.get("level", 1)) or 1
        level = max(1, min(6, level))
        return ("#" * level) + " " + text
    if t == "bulletListItem":
        return "- " + text
    if t == "numberedListItem":
        # The Milkdown side will re-number; ``1.`` is fine for every row.
        return "1. " + text
    if t == "checkListItem":
        checked = bool(props.get("checked", False))
        return f"- [{'x' if checked else ' '}] {text}"
    if t == "quote":
        return "> " + text if text else "> "
    if t == "codeBlock":
        lang = str(props.get("language", "")).strip()
        return f"```{lang}\n{text}\n```"
    if t == "paragraph" or t == "":
        return text
    # Unknown block — surface as a quote line so the user notices.
    return f"> [unsupported block: {t}] {text}".rstrip()


def _blocks_to_markdown(blocks: Any) -> str:
    """Walk the BlockNote document and join the rendered blocks with
    blank lines between them. Trailing whitespace is stripped."""
    if not isinstance(blocks, list):
        return ""
    lines: list[str] = []
    for b in blocks:
        rendered = _block_to_markdown(b)
        if rendered is None:
            continue
        lines.append(rendered)
    return "\n\n".join(lines).rstrip()


def upgrade() -> None:
    bind = op.get_bind()

    # Step 1: add ``body`` nullable (we'll lock it down once backfilled).
    op.add_column(
        "wiki_pages",
        sa.Column("body", sa.Text(), nullable=True),
    )

    # Step 2: backfill — walk every page, convert its block JSON to a
    # markdown string. We do this row-by-row in Python so the transcode
    # logic stays in one (testable) place.
    rows = bind.execute(
        sa.text("SELECT id, content FROM wiki_pages")
    ).fetchall()
    for row in rows:
        page_id = row[0]
        raw = row[1]
        # Postgres returns JSONB as already-parsed Python objects via
        # asyncpg, but Alembic's sync session may give us either a
        # ``dict``/``list`` or a JSON string depending on dialect. Handle
        # both shapes.
        if isinstance(raw, (bytes, str)):
            try:
                blocks = json.loads(raw)
            except (TypeError, ValueError):
                blocks = []
        else:
            blocks = raw or []
        body = _blocks_to_markdown(blocks)
        bind.execute(
            sa.text("UPDATE wiki_pages SET body = :b WHERE id = :id"),
            {"b": body, "id": page_id},
        )

    # Step 3: lock body NOT NULL, drop the old JSONB column.
    op.alter_column("wiki_pages", "body", nullable=False)
    op.drop_column("wiki_pages", "content")


def downgrade() -> None:
    # Recreate ``content`` as an empty JSONB array. The body → blocks
    # round-trip isn't lossless (we'd need to re-parse markdown into
    # BlockNote's tree), so we accept a clean reset here — downgrade is
    # a recovery path, not a normal flow.
    op.add_column(
        "wiki_pages",
        sa.Column(
            "content",
            sa.dialects.postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
    )
    op.execute("UPDATE wiki_pages SET content = '[]'::jsonb")
    op.alter_column("wiki_pages", "content", nullable=False)
    op.drop_column("wiki_pages", "body")
