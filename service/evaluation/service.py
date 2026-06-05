"""Answer quality evaluation using a resident judge model."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from service.llm.client import ChatMessage, LLMClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from service.db.models import Message, MessageEvaluation

__all__ = [
    "AnswerEvaluation",
    "EvaluationDisabledError",
    "evaluate_answer",
    "judge_message_for_user",
]


class EvaluationDisabledError(RuntimeError):
    """Raised when the judge feature is gated off via ``settings.evaluation.enabled``."""


@dataclass(frozen=True, slots=True)
class AnswerEvaluation:
    overall: int
    helpfulness: int
    groundedness: int
    citation_quality: int
    completeness: int
    risk: str
    comment: str
    raw: dict[str, Any]


_SYSTEM_PROMPT = """You are an answer-quality evaluator. Return ONLY valid JSON.
Score each dimension from 1 to 5.
Risk must be one of: low, medium, high.
Comment must be concise Chinese.
Do not include markdown fences."""


async def evaluate_answer(
    *,
    llm: LLMClient,
    model: str,
    question: str,
    answer: str,
    sources: list[dict[str, Any]] | None,
) -> AnswerEvaluation:
    source_text = _format_sources(sources or [])
    prompt = f"""Evaluate this assistant answer.

User question:
{question or "(unknown)"}

Assistant answer:
{answer}

Sources used by the answer:
{source_text or "(none)"}

Return JSON with exactly these keys:
overall, helpfulness, groundedness, citation_quality, completeness, risk, comment
"""
    chunks: list[str] = []
    async for chunk in llm.chat_stream(
        [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(role="user", content=prompt),
        ],
        model=model,
        tools=None,
    ):
        if chunk.delta:
            chunks.append(chunk.delta)
        if chunk.done:
            break
    raw_text = "".join(chunks).strip()
    parsed = _parse_json_object(raw_text)
    return AnswerEvaluation(
        overall=_score(parsed.get("overall")),
        helpfulness=_score(parsed.get("helpfulness")),
        groundedness=_score(parsed.get("groundedness")),
        citation_quality=_score(parsed.get("citation_quality")),
        completeness=_score(parsed.get("completeness")),
        risk=_risk(parsed.get("risk")),
        comment=str(parsed.get("comment") or "评分完成。")[:1000],
        raw={"text": raw_text, "parsed": parsed},
    )


def _format_sources(sources: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for source in sources[:12]:
        rank = source.get("rank") or len(lines) + 1
        title = source.get("title") or source.get("source") or source.get("url") or "source"
        quote = source.get("quote") or ""
        url = source.get("url") or ""
        lines.append(f"[{rank}] {title}\nURL: {url}\nQUOTE: {quote[:1200]}")
    return "\n\n".join(lines)


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _score(value: object) -> int:
    if isinstance(value, bool):
        n = 3
    elif isinstance(value, (str, bytes, bytearray, int, float)):
        try:
            n = int(value)
        except ValueError:
            n = 3
    else:
        n = 3
    return max(1, min(5, n))


def _risk(value: object) -> str:
    text = str(value or "low").lower().strip()
    return text if text in {"low", "medium", "high"} else "low"


# ---------------------------------------------------------------------------
# High-level orchestration — used by the HTTP layer
# ---------------------------------------------------------------------------


async def judge_message_for_user(
    db_session: AsyncSession,
    *,
    message: Message,
    user_id: uuid.UUID,
    question: str,
) -> MessageEvaluation:
    """Run the judge on ``message`` and persist a :class:`MessageEvaluation` row.

    The caller owns the four pre-checks the HTTP layer cares about
    (feature toggle, ownership, role, idempotency) — this function
    assumes they have all passed and ``message.role == "assistant"``.

    Settings are read here so HTTP routes don't have to reach across the
    layer boundary. Raises :class:`EvaluationDisabledError` if the
    feature is off; bubbles upstream LLM exceptions otherwise.
    """
    from service.db.models import MessageEvaluation
    from service.llm.ollama import OllamaClient
    from settings import settings

    if not settings.evaluation.enabled:
        raise EvaluationDisabledError("evaluation is disabled")

    llm = OllamaClient(
        base_url=settings.ollama.base_url,
        chat_model=settings.evaluation.model,
        embed_model=settings.ollama.embed_model,
        timeout=float(settings.evaluation.timeout),
        api_key=settings.ollama.api_key,
    )
    try:
        evaluation = await evaluate_answer(
            llm=llm,
            model=settings.evaluation.model,
            question=question,
            answer=message.content,
            sources=message.sources,
        )
    finally:
        await llm.aclose()

    row = MessageEvaluation(
        message_id=message.id,
        session_id=message.session_id,
        user_id=user_id,
        model=settings.evaluation.model,
        overall=evaluation.overall,
        helpfulness=evaluation.helpfulness,
        groundedness=evaluation.groundedness,
        citation_quality=evaluation.citation_quality,
        completeness=evaluation.completeness,
        risk=evaluation.risk,
        comment=evaluation.comment,
        raw=evaluation.raw,
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row
