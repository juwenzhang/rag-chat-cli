"""Tool-loop helpers — dedup keys, per-tool limits, history compaction,
auto-web-search heuristic.

Pulled out of :mod:`service.chat.service` so the orchestrator file stays
focused on the streaming state machine. All callers are inside the
``service.chat`` package.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from service.llm.client import ChatMessage, ToolCall

__all__ = [
    "build_web_search_query",
    "compact_context_text",
    "compact_history_tool_messages",
    "compact_tool_result_for_history",
    "drop_orphan_tool_messages",
    "pair_safe_recent_split",
    "should_auto_web_search",
    "tool_call_key",
    "tool_turn_limit",
]


def tool_call_key(call: ToolCall) -> str:
    """Stable dedup key for a tool invocation (name + canonical-JSON args)."""
    try:
        args = json.dumps(call.arguments, sort_keys=True, ensure_ascii=False, default=str)
    except TypeError:
        args = repr(call.arguments)
    return f"{call.name}:{args}"


def tool_turn_limit(name: str) -> int | None:
    """Per-tool cap on invocations within one generation turn (``None`` = uncapped)."""
    if name == "web_search":
        return 1
    if name == "web_fetch":
        return 2
    return None


def build_web_search_query(text: str) -> str:
    """Collapse whitespace and clip to a 240-char query budget."""
    query = " ".join(text.split())
    if len(query) <= 240:
        return query
    return query[:239].rstrip() + "…"


def compact_context_text(text: str, *, max_chars: int) -> str:
    """Single-line, length-clipped helper used by every history compactor."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max(0, max_chars - 1)].rstrip() + "…"


def compact_history_tool_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Apply :func:`compact_tool_result_for_history` to every ``tool`` row."""
    compacted: list[ChatMessage] = []
    for message in messages:
        if message.role != "tool":
            compacted.append(message)
            continue
        content = compact_tool_result_for_history(message.content, message.tool_name)
        compacted.append(
            ChatMessage(
                role="tool",
                content=content,
                tool_call_id=message.tool_call_id,
                tool_name=message.tool_name,
            )
        )
    return compacted


def compact_tool_result_for_history(content: str, tool_name: str | None) -> str:
    """Shrink a verbose tool payload before re-feeding it into the prompt.

    ``web_search`` keeps the first 5 ``(title, url)`` pairs; ``web_fetch``
    keeps a 1.2k-char text preview. Anything else falls back to a 1.5k-char
    single-line clip so a runaway tool can't blow the token budget.
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return compact_context_text(content, max_chars=1_500)
    if not isinstance(data, dict):
        return compact_context_text(content, max_chars=1_500)

    if tool_name == "web_search" or "results" in data:
        compact: dict[str, Any] = {
            "summary": "Previous web_search result compacted for context budget.",
            "query": data.get("query"),
            "provider": data.get("provider"),
        }
        if data.get("warning"):
            compact["warning"] = data.get("warning")
        raw_results = data.get("results")
        results: list[dict[str, str]] = []
        if isinstance(raw_results, list):
            for item in raw_results[:5]:
                if not isinstance(item, dict):
                    continue
                title = compact_context_text(str(item.get("title") or ""), max_chars=160)
                url = str(item.get("url") or "")
                if title or url:
                    results.append({"title": title, "url": url})
        compact["results"] = results
        return json.dumps(compact, ensure_ascii=False)

    if tool_name == "web_fetch" or "text" in data:
        compact = {
            "summary": "Previous web_fetch result compacted for context budget.",
            "title": data.get("title"),
            "url": data.get("url"),
            "provider": data.get("provider"),
            "text": compact_context_text(str(data.get("text") or ""), max_chars=1_200),
        }
        return json.dumps(compact, ensure_ascii=False)

    return compact_context_text(content, max_chars=1_500)


# ---------------------------------------------------------------------------
# Tool-call pairing helpers
# ---------------------------------------------------------------------------
#
# Most chat APIs (OpenAI, Anthropic via tool-use, Ollama tool calls) are
# strict about the structural pairing:
#
#   assistant(tool_calls=[c1, c2, ...]) → tool(tool_call_id=c1.id) → tool(c2.id)
#
# Drop or split through such a pair and the model will see a dangling
# ``tool_call_id`` with no originating assistant message — every provider we
# integrate with reacts to that by either erroring out or, worse, silently
# returning an empty assistant turn. The orchestrator then renders the
# "I gathered supporting sources but the model did not produce a final
# answer" fallback even though the real fault was upstream.
#
# These two helpers give the context-window machinery (``trim_to_budget`` /
# ``HistorySummarizer``) a way to respect those boundaries without each
# call site re-deriving the rules.


def drop_orphan_tool_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Remove ``tool`` messages whose originating ``assistant`` is gone.

    A ``tool`` row is "orphaned" if no preceding ``assistant`` message in
    the same list declared its ``tool_call_id`` inside ``tool_calls``.
    Trimming the head of a conversation can easily produce orphans (the
    earliest assistant turn that requested the tools got dropped, but the
    tool results survived because they sit later in the list); shipping
    those to the LLM raises a 400 on every strict provider.

    Returns a *new* list — input is not mutated.
    """
    known_ids: set[str] = set()
    out: list[ChatMessage] = []
    for msg in messages:
        if msg.role == "assistant" and msg.tool_calls:
            for tc in msg.tool_calls:
                known_ids.add(tc.id)
            out.append(msg)
            continue
        if msg.role == "tool":
            if msg.tool_call_id and msg.tool_call_id in known_ids:
                out.append(msg)
            # else: orphan, drop silently.
            continue
        out.append(msg)
    return out


def pair_safe_recent_split(
    messages: list[ChatMessage],
    *,
    keep_recent: int,
) -> tuple[list[ChatMessage], list[ChatMessage]]:
    """Split into ``(older, recent)`` without cutting through a tool pair.

    The naive ``messages[:-N], messages[-N:]`` split is what the original
    :class:`HistorySummarizer` used; it can land the cut between an
    ``assistant(tool_calls=...)`` row and its matching ``tool`` rows,
    leaving ``recent`` with dangling ``tool_call_id`` references that the
    LLM cannot resolve.

    This helper aims for a target of ``keep_recent`` trailing messages but
    walks the boundary backwards (towards older) until it sits *before*
    any ``assistant(tool_calls)`` whose tool-result rows are inside
    ``recent``. The returned split therefore satisfies:

    * ``older + recent == messages`` (lossless)
    * No ``tool`` row in ``recent`` references a ``tool_call_id`` from a
      message in ``older``.

    ``keep_recent`` is treated as a *minimum* — the realised ``recent``
    can be longer when boundary alignment requires it. ``older`` may
    therefore be empty for short conversations.
    """
    if keep_recent <= 0:
        return list(messages), []
    if len(messages) <= keep_recent:
        return [], list(messages)

    boundary = len(messages) - keep_recent

    # Walk the boundary left as long as messages[boundary] is a ``tool``
    # row whose originating assistant is at messages[boundary-1] (or
    # earlier in the same contiguous tool block). We need to land *on*
    # that originating assistant message at the latest, so that everything
    # to the right of the split is self-contained.
    while boundary > 0 and _split_breaks_tool_pair(messages, boundary):
        boundary -= 1

    return messages[:boundary], messages[boundary:]


def _split_breaks_tool_pair(messages: list[ChatMessage], boundary: int) -> bool:
    """True when slicing at ``boundary`` would orphan a tool result.

    The cut is unsafe when:

    * ``messages[boundary]`` is itself a ``tool`` row (its assistant
      sibling is to the left of the cut), OR
    * any ``tool`` row at index ``>= boundary`` has its
      ``tool_call_id`` declared by an assistant message at index
      ``< boundary``.
    """
    head = messages[boundary]
    if head.role == "tool":
        return True

    # Build the set of tool_call_ids that are introduced *inside* recent.
    introduced_in_recent: set[str] = set()
    for msg in messages[boundary:]:
        if msg.role == "assistant" and msg.tool_calls:
            for tc in msg.tool_calls:
                introduced_in_recent.add(tc.id)

    for msg in messages[boundary:]:
        if (
            msg.role == "tool"
            and msg.tool_call_id is not None
            and msg.tool_call_id not in introduced_in_recent
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Auto web-search heuristic
# ---------------------------------------------------------------------------

_WEB_SEARCH_OFF_MARKERS = (
    "不要联网",
    "不用联网",
    "不要搜索",
    "不用搜索",
    "仅根据本地",
    "只根据本地",
    "no web",
    "don't search",
    "do not search",
)

_WEB_SEARCH_STRONG_MARKERS = (
    "最新",
    "当前",
    "现在",
    "今天",
    "实时",
    "近期",
    "官方",
    "官网",
    "文档",
    "资料来源",
    "引用",
    "来源",
    "查一下",
    "搜索",
    "联网",
    "202",
    "latest",
    "current",
    "today",
    "official",
    "docs",
    "documentation",
    "source",
    "citation",
)

_WEB_SEARCH_RESEARCH_MARKERS = (
    "深度",
    "总结",
    "综述",
    "调研",
    "对比",
    "比较",
    "最佳实践",
    "架构",
    "原理",
    "核心概念",
    "deep dive",
    "research",
    "survey",
    "compare",
    "best practice",
    "architecture",
    "core concept",
)


def should_auto_web_search(
    text: str,
    *,
    mode: bool | Literal["auto", "always", "off"],
    has_local_hits: bool,
) -> bool:
    """Decide whether the auto-web-search guardrail should fire.

    ``mode`` is the user-set policy: ``True`` / ``"always"`` always fires,
    ``False`` / ``"off"`` never fires, ``"auto"`` runs the keyword
    heuristic. The keyword set is intentionally bilingual (zh/en) so a
    mixed-language prompt resolves the same way in both surfaces.
    """
    if mode is True or mode == "always":
        return True
    if mode is False or mode == "off":
        return False

    normalized = " ".join(text.lower().split())
    if not normalized:
        return False
    if any(marker in normalized for marker in _WEB_SEARCH_OFF_MARKERS):
        return False
    if any(marker in normalized for marker in _WEB_SEARCH_STRONG_MARKERS):
        return True
    if any(marker in normalized for marker in _WEB_SEARCH_RESEARCH_MARKERS):
        return not has_local_hits or len(normalized) >= 24
    return False
