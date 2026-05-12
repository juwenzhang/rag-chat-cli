"""History compression — summarize old turns when the conversation overflows.

When :class:`core.chat_service.ChatService` is about to call the LLM with
a message list that exceeds the configured :class:`~core.tokens.TokenBudget`,
:class:`HistorySummarizer` rewrites the oldest turns into a single
``role="system"`` "Earlier-conversation summary" message. The most recent
turns are kept verbatim — the user expects continuity on what they just said.

The summarizer is intentionally LLM-backed (not heuristic) — the model that
generates replies is already loaded, so reusing it for summarization avoids
shipping a separate text-summarization stack. Cost is one short generation
per overflow event.

If no :class:`HistorySummarizer` is wired up, callers fall back to
:func:`core.tokens.trim_to_budget` which simply drops old turns. The
summarizer is therefore additive: every code path that calls it must
keep working without it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.llm.client import ChatMessage, LLMError
from core.tokens import TokenBudget, Tokenizer, trim_to_budget

if TYPE_CHECKING:
    from core.llm.client import LLMClient

__all__ = ["HistorySummarizer"]

logger = logging.getLogger(__name__)


_SUMMARY_INSTRUCTION = (
    "You will be shown a transcript of an earlier conversation. Produce a "
    "concise factual summary (max 6 short bullet points) capturing: user "
    "intents, decisions reached, names / numbers / identifiers introduced, "
    "and any open questions. Do NOT roleplay, do NOT continue the "
    "conversation — output the summary only."
)

_SUMMARY_PREFIX = "Earlier-conversation summary:\n"


class HistorySummarizer:
    """Compress old turns into a single summary when the budget overflows.

    ``keep_recent`` is the number of trailing messages that survive
    untouched. The default (6) preserves a few back-and-forth turns —
    enough that the user's last few utterances stay verbatim while the
    pre-history is collapsed.
    """

    def __init__(
        self,
        *,
        llm: LLMClient,
        tokenizer: Tokenizer,
        summarizer_model: str | None = None,
        keep_recent: int = 6,
    ) -> None:
        self._llm = llm
        self._tokenizer = tokenizer
        self._summarizer_model = summarizer_model
        self._keep_recent = max(1, keep_recent)

    async def compress(
        self,
        messages: list[ChatMessage],
        *,
        budget: TokenBudget,
    ) -> list[ChatMessage]:
        """Compress old turns if needed; return the (possibly shrunken) list.

        Pipeline:

        1. If the list already fits the budget → return unchanged.
        2. Split into ``[leading_system?] + older + recent`` where
           ``recent`` is the last ``keep_recent`` turns.
        3. Ask the LLM to summarize ``older`` into one bullet block.
        4. Return ``[leading_system?, summary_as_system, *recent]``.
        5. If even that exceeds the budget, fall back to ``trim_to_budget``
           on the resulting list (which may further drop the summary or
           older recent turns).

        Errors from the summarizer LLM call are logged and the function
        falls back to plain :func:`trim_to_budget` — context management
        must never block the main reply path.
        """
        if not messages:
            return messages

        used = self._tokenizer.count_messages(messages)
        if budget.fits(used):
            return messages

        leading_system: ChatMessage | None = None
        body = list(messages)
        if body and body[0].role == "system":
            leading_system = body.pop(0)

        if len(body) <= self._keep_recent:
            # Not enough older content to summarize — fall back to trim.
            return trim_to_budget(messages, tokenizer=self._tokenizer, budget=budget)

        older = body[: -self._keep_recent]
        recent = body[-self._keep_recent :]

        try:
            summary_text = await self._summarize(older)
        except LLMError as exc:
            logger.warning("history summarization failed: %s — falling back to trim", exc)
            return trim_to_budget(messages, tokenizer=self._tokenizer, budget=budget)

        summary_msg = ChatMessage(role="system", content=_SUMMARY_PREFIX + summary_text)
        rebuilt = (
            ([leading_system] if leading_system is not None else [])
            + [summary_msg]
            + recent
        )

        # Even after summarization, the rebuilt list may still overflow
        # (e.g. ``recent`` itself is huge). Tighten with trim_to_budget.
        if not budget.fits(self._tokenizer.count_messages(rebuilt)):
            rebuilt = trim_to_budget(rebuilt, tokenizer=self._tokenizer, budget=budget)
        return rebuilt

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _summarize(self, older: list[ChatMessage]) -> str:
        """Run a one-shot LLM call to summarize ``older``. Returns the body text."""
        transcript_lines: list[str] = []
        for m in older:
            label = m.role
            if m.tool_calls:
                names = ", ".join(tc.name for tc in m.tool_calls)
                transcript_lines.append(f"[{label} called tools: {names}]")
            content = m.content.strip()
            if content:
                transcript_lines.append(f"[{label}] {content}")
        transcript = "\n".join(transcript_lines)

        prompt = [
            ChatMessage(role="system", content=_SUMMARY_INSTRUCTION),
            ChatMessage(role="user", content=transcript),
        ]

        collected: list[str] = []
        async for chunk in self._llm.chat_stream(prompt, model=self._summarizer_model):
            if chunk.delta:
                collected.append(chunk.delta)
        text = "".join(collected).strip()
        if not text:
            raise LLMError("summarizer LLM returned empty output")
        return text
