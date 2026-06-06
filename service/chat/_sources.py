"""Source / citation list builders + small chat-side string helpers.

* :func:`sources_from_hits` — pgvector hits → UI-side ``sources`` rows.
* :func:`sources_from_tool_result` — tool result metadata → ``sources`` rows.
* :func:`empty_answer_fallback` — placeholder when the LLM produces no text.
* :func:`maybe_uuid` — best-effort UUID parse for ``user_memories`` FK.

All four are pure functions extracted from :mod:`service.chat.service` to
keep the orchestrator file focused on the state machine.
"""

from __future__ import annotations

import uuid
from typing import Any

from service.knowledge.base import KnowledgeHit
from service.tools import ToolResult

__all__ = [
    "WEB_EVIDENCE_INSTRUCTION",
    "empty_answer_fallback",
    "maybe_uuid",
    "sources_from_hits",
    "sources_from_tool_result",
]


WEB_EVIDENCE_INSTRUCTION = (
    "Use the following web/tool evidence for factual claims when relevant. Evidence may be "
    "compressed; do not assume omitted details. Preserve exact option names, commands, "
    "versions, defaults, and caveats. If evidence is insufficient, state the gap explicitly."
)


def empty_answer_fallback(sources: list[dict[str, Any]]) -> str:
    """Placeholder text when the model finished a turn with empty content.

    Two shapes:

    * **Sources collected** — the ReAct loop ran tools, gathered evidence,
      but the synthesis turn returned an empty assistant message. The
      most common root causes are (a) a context-window overflow that
      causes the upstream provider to silently truncate, or (b) a
      malformed tool-call/result pairing left behind by trimming. The
      surface message hints at retry + checking the sources panel.
    * **No sources** — the model stopped on the very first turn with no
      output. Almost always a transient upstream hiccup; ask for retry.
    """
    if sources:
        return (
            "I gathered supporting sources for this question but the model "
            "didn't produce a final answer this round — usually caused by "
            "a context-window overflow on a long ReAct trace. Please retry "
            "(or open the sources panel to inspect the evidence already "
            "collected)."
        )
    return "The model stopped before producing a final answer. Please retry."


def sources_from_hits(hits: list[KnowledgeHit]) -> list[dict[str, Any]]:
    """Render pgvector :class:`KnowledgeHit` s as wire-format ``sources`` rows."""
    sources: list[dict[str, Any]] = []
    for rank, hit in enumerate(hits, start=1):
        source: dict[str, Any] = {
            "source_type": "document",
            "rank": rank,
            "title": hit.title,
            "quote": hit.content,
            "score": hit.score,
            "source": hit.source,
        }
        if hit.document_id is not None:
            source["document_id"] = hit.document_id
        if hit.chunk_id is not None:
            source["chunk_id"] = hit.chunk_id
        sources.append(source)
    return sources


def sources_from_tool_result(result: ToolResult, *, start_rank: int) -> list[dict[str, Any]]:
    """Pull ``metadata.sources`` off a :class:`ToolResult` and rank them."""
    metadata = result.metadata or {}
    raw_sources = metadata.get("sources")
    if not isinstance(raw_sources, list):
        return []
    sources: list[dict[str, Any]] = []
    rank = start_rank
    for raw in raw_sources:
        if not isinstance(raw, dict):
            continue
        source = dict(raw)
        source.setdefault("source_type", "tool")
        source["rank"] = rank
        rank += 1
        sources.append(source)
    return sources


def maybe_uuid(s: str) -> uuid.UUID | None:
    """Best-effort UUID parse — returns ``None`` instead of raising.

    Used to convert the opaque ``session_id`` passed to
    :meth:`ChatService.generate` into a foreign key for
    ``user_memories.source_session_id``. Tokens that don't parse as
    UUIDs degrade to ``None``, which is the intended behaviour
    (no FK to attach).
    """
    try:
        return uuid.UUID(s)
    except (ValueError, TypeError):
        return None
