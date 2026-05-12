"""Auto-reflect critic — judges whether a Q+A is worth caching to the KB.

The critic is a small LLM call that runs after a successful turn. It
emits a strict-JSON verdict; if ``save=true`` and ``confidence`` clears
the user's threshold, the orchestrator persists a "fact card" into the
local KB so future similar queries can retrieve it without re-asking
the model.

The prompt deliberately enumerates **both** SAVE and SKIP heuristics so
the model doesn't drift toward "save everything" or "save nothing" over
time. The JSON contract is the lowest-risk format we can ask of a small
local model — bracket-matched, no markdown, no prose.

Parsing is forgiving: a model that wraps the JSON in a ``` fence or
prepends "Sure, here you go:" still gets handled by
:func:`_extract_json`. A model that returns nonsense yields ``None`` so
the caller can quietly skip rather than crash the REPL.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.llm.client import LLMClient

__all__ = [
    "KB_REFLECT_PROMPT",
    "ReflectionCritic",
    "ReflectionResult",
]

logger = logging.getLogger(__name__)


KB_REFLECT_PROMPT = """\
You are a knowledge curator. Decide whether the following Q&A is worth
saving to a personal knowledge base for future retrieval.

SAVE IT IF:
- The answer contains a concrete, reusable fact, procedure, or insight
  the user is likely to need again (e.g. a config recipe, a fix, a
  domain-specific definition, a step list, a non-trivial command).
- The answer is self-contained — readable without the surrounding
  conversation.

DO NOT SAVE IF:
- It's casual chit-chat, greetings, or pure opinion.
- It's time-sensitive (prices, news, "today" only).
- The answer is uncertain ("I'm not sure", "it depends", heavy hedging).
- It restates trivially-known information (basic syntax, math facts).
- It contains secrets (API keys, passwords, personal IDs, tokens).

Respond with STRICT JSON, no markdown, no prose, no code fence:
{{
  "save": <true|false>,
  "confidence": <number between 0.0 and 1.0>,
  "title": "<concise topic, ≤60 chars, empty string if save=false>",
  "summary": "<200-400 char standalone fact card. Include keywords for search. Empty if save=false.>",
  "tags": ["<tag1>", "<tag2>"]
}}

---
USER QUESTION:
{question}

---
ASSISTANT ANSWER:
{answer}
"""


@dataclass(frozen=True, slots=True)
class ReflectionResult:
    """Parsed verdict from the critic LLM call."""

    save: bool
    confidence: float
    title: str
    summary: str
    tags: list[str]


def _extract_json(text: str) -> str | None:
    """Pull the first balanced JSON object out of ``text``.

    Handles three common LLM behaviors:
      1. Pure JSON, no wrappers (the happy path).
      2. JSON wrapped in a ```json ... ``` fence (Markdown habit).
      3. JSON preceded/followed by prose ("Here is the verdict: {...}").

    Returns ``None`` if no balanced object is found — caller treats that
    as "skip this turn" rather than crashing.
    """
    stripped = text.strip()
    # Fenced form: pull the body. We don't care about the language tag.
    if stripped.startswith("```"):
        first_nl = stripped.find("\n")
        if first_nl != -1:
            stripped = stripped[first_nl + 1 :]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
        stripped = stripped.strip()

    start = stripped.find("{")
    if start == -1:
        return None
    # Find the matching closing brace by tracking depth. String state
    # has to be honoured so a ``}`` inside a string doesn't end the scan.
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(stripped)):
        ch = stripped[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : i + 1]
    return None


class ReflectionCritic:
    """Runs the critic prompt and returns a parsed verdict (or ``None``).

    Construct once per chat session; ``judge()`` is safe to call from
    multiple turns. The critic is intentionally LLM-agnostic — it only
    needs ``LLMClient.chat_stream`` so swapping providers (Ollama →
    OpenAI) requires no changes here.

    ``model`` overrides the LLM's default chat model — useful if you
    want the critic to run on a tiny model while the main chat uses a
    bigger one. ``None`` lets the LLMClient pick its own default.
    """

    def __init__(
        self,
        *,
        llm: LLMClient,
        model: str | None = None,
    ) -> None:
        self._llm = llm
        self._model = model

    async def judge(self, question: str, answer: str) -> ReflectionResult | None:
        if not question.strip() or not answer.strip():
            return None
        from core.llm.client import ChatMessage

        prompt = KB_REFLECT_PROMPT.format(
            question=question.strip(),
            answer=answer.strip(),
        )
        messages = [ChatMessage(role="user", content=prompt)]
        parts: list[str] = []
        try:
            async for chunk in self._llm.chat_stream(messages, model=self._model):
                delta = chunk.delta or ""
                if delta:
                    parts.append(delta)
                if chunk.done:
                    break
        except Exception as exc:
            logger.warning("ReflectionCritic: LLM call failed: %s", exc)
            return None

        raw = "".join(parts)
        payload = _extract_json(raw)
        if payload is None:
            logger.debug("ReflectionCritic: no JSON found in response: %r", raw[:200])
            return None
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            logger.debug("ReflectionCritic: JSON parse failed (%s): %r", exc, payload[:200])
            return None
        if not isinstance(data, dict):
            return None
        try:
            save = bool(data.get("save", False))
            confidence = float(data.get("confidence", 0.0))
            title = str(data.get("title") or "")
            summary = str(data.get("summary") or "")
            tags_raw = data.get("tags") or []
            tags = (
                [str(t) for t in tags_raw if isinstance(t, (str, int, float))]
                if isinstance(tags_raw, list)
                else []
            )
        except (TypeError, ValueError) as exc:
            logger.debug("ReflectionCritic: field coercion failed: %s", exc)
            return None
        confidence = max(0.0, min(1.0, confidence))
        return ReflectionResult(
            save=save,
            confidence=confidence,
            title=title,
            summary=summary,
            tags=tags,
        )
