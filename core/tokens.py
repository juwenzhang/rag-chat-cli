"""Token counting + budget arithmetic (#14 P3.1).

The :class:`Tokenizer` Protocol is the seam between :class:`~core.llm.client.LLMClient`
implementations (each provider has a different real tokenizer) and the
context-management helpers in :mod:`core.chat_service` (history summarization,
trim-to-fit, prompt budget).

The default :class:`CharApproxTokenizer` exists so the rest of the system
can keep working without pulling in ``tiktoken`` or model-specific tokenizers
as a hard dependency. It uses the well-known "≈ 4 chars per token for
English, ≈ 2 for CJK" heuristic — fine for budget arithmetic on long
documents, off by ±20% on short / mixed-language strings. When that matters,
construct a real tokenizer (a future ``TiktokenTokenizer`` / per-model class)
and pass it in explicitly.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from core.llm.client import ChatMessage

__all__ = [
    "CharApproxTokenizer",
    "TokenBudget",
    "Tokenizer",
    "trim_to_budget",
]


@runtime_checkable
class Tokenizer(Protocol):
    """Minimum tokenizer contract used by context-window helpers.

    Implementations should be *fast* (called per-message, possibly per
    turn) and *deterministic* — the same text always yields the same
    count. Tokenization of the LLM-facing wire format (system / user /
    assistant / tool, plus separator overhead) is the impl's job, not
    the caller's.
    """

    def count_text(self, text: str) -> int:
        """Tokens in a raw string."""
        ...

    def count_message(self, message: ChatMessage) -> int:
        """Tokens in one :class:`ChatMessage` including role/separator overhead."""
        ...

    def count_messages(self, messages: list[ChatMessage]) -> int:
        """Tokens in a list of messages (sum of ``count_message`` + framing)."""
        ...


# ---------------------------------------------------------------------------
# Default approximation tokenizer
# ---------------------------------------------------------------------------

# Per-message overhead approximating the chat-template framing tokens that
# every modern provider injects around each message ("<|im_start|>role\n...
# <|im_end|>\n" or similar). Conservatively 4 tokens per message.
_PER_MESSAGE_OVERHEAD = 4

# Extra framing tokens added once around the whole conversation
# (priming tokens, BOS/EOS, etc). Conservative 3.
_PER_CONVERSATION_OVERHEAD = 3


def _is_cjk(char: str) -> bool:
    """Heuristic: is this codepoint visually a CJK ideograph or kana?

    Used by :class:`CharApproxTokenizer` to apply a denser tokens-per-char
    ratio for CJK text (where one character ≈ one token in BPE vocabularies
    trained on Chinese / Japanese / Korean).
    """
    name = unicodedata.name(char, "")
    if not name:
        return False
    return (
        name.startswith("CJK ")
        or name.startswith("HIRAGANA ")
        or name.startswith("KATAKANA ")
        or name.startswith("HANGUL ")
    )


@dataclass(frozen=True, slots=True)
class CharApproxTokenizer:
    """Character-ratio tokenizer — the framework default.

    ``chars_per_token_ascii=4`` matches the OpenAI rule of thumb for
    English. ``chars_per_token_cjk=1`` reflects that BPE vocabularies
    spend roughly one token per CJK glyph. Hybrid text is counted by
    classifying each character and applying the corresponding rate.
    """

    chars_per_token_ascii: float = 4.0
    chars_per_token_cjk: float = 1.0

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        ascii_chars = 0
        cjk_chars = 0
        for ch in text:
            if _is_cjk(ch):
                cjk_chars += 1
            else:
                ascii_chars += 1
        ascii_tokens = ascii_chars / max(self.chars_per_token_ascii, 1e-9)
        cjk_tokens = cjk_chars / max(self.chars_per_token_cjk, 1e-9)
        # Always round up — under-counting is the dangerous direction
        # (we'd over-fill the context window). One extra token per call
        # is cheap insurance.
        return max(1, int(ascii_tokens + cjk_tokens + 0.999))

    def count_message(self, message: ChatMessage) -> int:
        total = self.count_text(message.content) + _PER_MESSAGE_OVERHEAD
        # Tool-call payloads ride on the wire as JSON; count their args
        # generously by stringifying argument values.
        if message.tool_calls:
            for tc in message.tool_calls:
                total += self.count_text(tc.name) + self.count_text(str(tc.arguments))
        if message.tool_call_id:
            total += self.count_text(message.tool_call_id)
        return total

    def count_messages(self, messages: list[ChatMessage]) -> int:
        return sum(self.count_message(m) for m in messages) + _PER_CONVERSATION_OVERHEAD


# ---------------------------------------------------------------------------
# Budget arithmetic
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TokenBudget:
    """A scalar budget with a few sanity checks.

    Treat as the *input* budget for one LLM call. Reply tokens are
    reserved separately via ``reserve_for_reply`` so the helper can
    enforce ``input + reply <= context_window``.

    Typical use::

        budget = TokenBudget(max_tokens=8192, reserve_for_reply=1024)
        kept = trim_to_budget(messages, tokenizer=tk, budget=budget)
    """

    max_tokens: int
    reserve_for_reply: int = 0

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")
        if self.reserve_for_reply < 0:
            raise ValueError("reserve_for_reply must be non-negative")
        if self.reserve_for_reply >= self.max_tokens:
            raise ValueError(
                f"reserve_for_reply ({self.reserve_for_reply}) must be smaller "
                f"than max_tokens ({self.max_tokens})"
            )

    @property
    def input_budget(self) -> int:
        """Tokens available for the input messages (max_tokens - reserve)."""
        return self.max_tokens - self.reserve_for_reply

    def fits(self, used: int) -> bool:
        return used <= self.input_budget

    def remaining(self, used: int) -> int:
        return max(0, self.input_budget - used)


def trim_to_budget(
    messages: list[ChatMessage],
    *,
    tokenizer: Tokenizer,
    budget: TokenBudget,
    keep_leading_system: bool = True,
) -> list[ChatMessage]:
    """Drop oldest non-system messages until the list fits ``budget``.

    Order of preservation:

    1. The leading ``role="system"`` message (if any and ``keep_leading_system``)
       — always kept; trimmed text never violates priming.
    2. The last (most recent) message — always kept; that's the message
       the LLM is actually answering.
    3. Earlier turns — dropped oldest-first until the total fits.

    Returns the surviving subset. If even after dropping everything except
    (1) + (last) the list still exceeds the budget, the result is returned
    as-is — the caller is expected to swap in :mod:`core.history` (#15) or
    truncate the last message's content.
    """
    if not messages:
        return messages

    leading_system: ChatMessage | None = None
    body = list(messages)
    if keep_leading_system and body and body[0].role == "system":
        leading_system = body.pop(0)

    if not body:
        # Just a system message; trivially fits or won't fit either way.
        return [leading_system] if leading_system is not None else []

    last = body[-1]
    middle = body[:-1]

    def total(parts: list[ChatMessage]) -> int:
        wrapped = ([leading_system] if leading_system else []) + parts + [last]
        return tokenizer.count_messages(wrapped)

    # Fast path: already fits.
    if budget.fits(total(middle)):
        return ([leading_system] if leading_system else []) + middle + [last]

    # Drop oldest from ``middle`` until it fits or middle is empty.
    while middle and not budget.fits(total(middle)):
        middle.pop(0)

    return ([leading_system] if leading_system else []) + middle + [last]
