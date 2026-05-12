"""Session title generation — shared between CLI sidebar and REST API.

Two functions, used together as a two-stage strategy:

1. :func:`synthesize_preview_title` — pure, instant, fallback when no real
   title is stored yet. Takes the first non-empty user message and trims it.

2. :func:`generate_llm_title` — one short LLM call that produces a concise
   (≤16 char) title summarizing the conversation. Called fire-and-forget
   after the first assistant reply lands, then persisted via
   ``ChatMemory.set_title`` so the sidebar upgrades from preview → real.

Keeping both in one module means ``DbChatMemory.list_session_metas``,
``FileChatMemory.list_session_metas`` and the REST ``GET /chat/sessions``
endpoint all agree on the fallback rule.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.llm.client import ChatMessage, LLMError

if TYPE_CHECKING:
    from core.llm.client import LLMClient

__all__ = ["generate_llm_title", "synthesize_preview_title"]


_PREVIEW_DEFAULT_CHARS = 24
_LLM_TITLE_MAX_CHARS = 16
_LLM_TITLE_PROMPT = (
    "Read the conversation below and write a concise title for it "
    "in the same language as the user. "
    "Strict rules: ≤16 characters, no quotes, no trailing punctuation, "
    "no prefix like 'Title:'. Output only the title text."
)


def synthesize_preview_title(
    messages: list[ChatMessage],
    *,
    max_chars: int = _PREVIEW_DEFAULT_CHARS,
) -> str:
    """Pure, instant title from the first user message — used as a fallback.

    Returns ``"(empty)"`` when there is no user message yet so the sidebar
    never shows a blank row.
    """
    for msg in messages:
        if msg.role == "user" and msg.content.strip():
            text = msg.content.strip().replace("\n", " ")
            if len(text) <= max_chars:
                return text
            return text[:max_chars] + "…"
    return "(empty)"


async def generate_llm_title(
    messages: list[ChatMessage],
    llm: LLMClient,
    *,
    model: str | None = None,
    max_chars: int = _LLM_TITLE_MAX_CHARS,
) -> str:
    """Ask the LLM for a short title summarizing ``messages``.

    Re-uses the chat-completion path (``chat_stream``) so we don't need a
    separate text-generation API. Cost is one short generation, run only
    once per session lifecycle (after the first assistant turn).

    Returns a stripped, sanitized title bounded by ``max_chars``. Raises
    :class:`LLMError` if the model returns nothing usable — callers should
    treat this as non-fatal and fall back to the preview title.
    """
    transcript = _format_transcript(messages, limit=6)
    prompt: list[ChatMessage] = [
        ChatMessage(role="system", content=_LLM_TITLE_PROMPT),
        ChatMessage(role="user", content=transcript),
    ]

    pieces: list[str] = []
    async for chunk in llm.chat_stream(prompt, model=model):
        if chunk.content:
            pieces.append(chunk.content)
    raw = "".join(pieces).strip()
    if not raw:
        raise LLMError("title generation returned empty output")
    return _clean_title(raw, max_chars=max_chars)


def _format_transcript(messages: list[ChatMessage], *, limit: int) -> str:
    """Render the last ``limit`` user/assistant turns as a compact transcript."""
    relevant = [m for m in messages if m.role in ("user", "assistant") and m.content.strip()]
    tail = relevant[-limit:]
    lines = []
    for m in tail:
        prefix = "User" if m.role == "user" else "Assistant"
        body = m.content.strip().replace("\n", " ")
        if len(body) > 400:
            body = body[:400] + "…"
        lines.append(f"{prefix}: {body}")
    return "\n".join(lines)


def _clean_title(raw: str, *, max_chars: int) -> str:
    """Strip surrounding noise and clamp to ``max_chars``.

    LLMs sometimes prepend "Title:", wrap in quotes, or append a period
    even after being told not to. Cheap to clean here, expensive to
    retry-prompt.
    """
    text = raw.strip()
    for prefix in ("Title:", "title:", "标题:", "标题：", "Subject:"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
    text = text.strip("\"'`“”‘’ ")
    text = text.rstrip(".。!！?？,，;；:：")
    text = text.replace("\n", " ").strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "…"
    return text or "(empty)"
