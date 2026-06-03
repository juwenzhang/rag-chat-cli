"""High-level chat orchestration — ReAct loop.

:class:`ChatService` is the single seam between :mod:`app` and the rest of
:mod:`core`. It owns an :class:`~service.llm.client.LLMClient`, a
:class:`~service.memory.chat_memory.ChatMemory`, an optional retriever and an
optional :class:`~service.tools.ToolRegistry`, and exposes one async generator
:meth:`generate` that drives a bounded **reason-act** loop:

  user → (retrieval?) → ⤺ [ assistant → (tool_calls?) → tool_results ] → done

Each iteration calls the LLM with the running conversation; if the LLM emits
``tool_calls``, the registry dispatches them, results are spliced back into
the conversation as ``role="tool"`` messages, and the loop iterates. When the
LLM emits a tool-free assistant turn the loop terminates with a ``done``
event. ``max_steps`` caps the loop so a misbehaving model can't spin forever.

Emitted event types (see :mod:`core.streaming.events`):

* ``retrieval`` — when ``use_rag`` and a KB is configured.
* ``token`` — incremental assistant text deltas.
* ``tool_call`` — assistant requested a tool invocation (one per call).
* ``tool_result`` — the dispatched tool's outcome.
* ``done`` — terminal happy path.
* ``error`` — terminal failure (``llm_error`` / ``memory_*`` /
  ``max_steps_reached`` / ``ABORTED`` / ``unexpected``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, ClassVar, Literal

from service.chat.history import HistorySummarizer
from service.chat.limits import DEFAULT_LIMITS, ResourceLimits
from service.chat.prompts import DEFAULT_TEMPLATES, PromptBuilder
from service.chat.tokens import TokenBudget, Tokenizer, trim_to_budget
from service.common.observability import UsageAccumulator, get_tracer
from service.knowledge.base import KnowledgeBase, KnowledgeHit
from service.llm.client import ChatMessage, LLMClient, LLMError, ThinkingMode, ToolCall, ToolSpec
from service.memory.chat_memory import ChatMemory
from service.memory.user_memory import FactExtractor, UserMemoryEntry, UserMemoryStore
from service.streaming.abort import AbortContext
from service.streaming.events import Event
from service.tools import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)

_tracer = get_tracer(__name__)

__all__ = ["ChatService"]


class ChatService:
    """Glue between LLM, memory, retriever and tool registry."""

    def __init__(
        self,
        llm: LLMClient,
        memory: ChatMemory,
        knowledge: KnowledgeBase | None = None,
        tools: ToolRegistry | None = None,
        tokenizer: Tokenizer | None = None,
        token_budget: TokenBudget | None = None,
        summarizer: HistorySummarizer | None = None,
        user_memory: UserMemoryStore | None = None,
        fact_extractor: FactExtractor | None = None,
        prompt_builder: PromptBuilder | None = None,
        system_prompt: str | None = None,
        limits: ResourceLimits | None = None,
        usage_accumulator: UsageAccumulator | None = None,
    ) -> None:
        self._llm = llm
        self._memory = memory
        self._kb = knowledge
        self._tools = tools
        self._tokenizer = tokenizer
        self._token_budget = token_budget
        self._summarizer = summarizer
        self._user_memory = user_memory
        self._fact_extractor = fact_extractor
        self._prompt_builder = prompt_builder or PromptBuilder(templates=DEFAULT_TEMPLATES)
        # ``system_prompt`` overrides the template default for *this* service
        # without mutating the shared :class:`PromptTemplates`. Pass an empty
        # string to suppress the persona system message entirely.
        self._system_prompt = system_prompt
        self._limits = limits or DEFAULT_LIMITS
        # ``UsageAccumulator`` is opt-in: callers that want token / cost
        # totals across many turns pass one in and read ``service.usage``.
        # Default ``None`` keeps the pre-#22 zero-overhead path.
        self._usage = usage_accumulator
        self._background_tasks: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------
    # Public introspection — orchestrators (app/) need to reach the memory
    # backend to render sidebars, set titles, etc. Exposed read-only.
    # ------------------------------------------------------------------
    @property
    def memory(self) -> ChatMemory:
        return self._memory

    @property
    def llm(self) -> LLMClient:
        """Underlying LLM client. Exposed so orchestrators can hot-rotate
        credentials (e.g. ``OllamaClient.set_api_key``) without rebuilding
        the whole ChatService."""
        return self._llm

    @property
    def tools(self) -> ToolRegistry | None:
        return self._tools

    @property
    def knowledge(self) -> KnowledgeBase | None:
        """The wired knowledge base, or ``None`` if RAG is disabled.

        Exposed so REPL slash commands (``/kb``, ``/save``) can inspect
        and mutate the underlying store without rebuilding ChatService.
        Type-narrow at the call site to access impl-specific methods
        like :meth:`~service.knowledge.local.FileKnowledgeBase.add_document`.
        """
        return self._kb

    @property
    def usage(self) -> UsageAccumulator | None:
        return self._usage

    # ------------------------------------------------------------------
    # Internal: context-window management
    # ------------------------------------------------------------------
    async def _dispatch_tool_with_timeout(
        self,
        tc: ToolCall,
        *,
        abort: AbortContext | None,
    ) -> ToolResult:
        """Wrap :meth:`ToolRegistry.dispatch` in a timeout and a cooperative
        abort race. A hung tool can't stall the loop past ``tool_timeout_s``;
        a client-side abort cancels the tool task immediately.

        Returns a :class:`ToolResult` either way — the registry already
        guarantees this for normal failures, and we wrap timeouts /
        cancellations in the same shape so the loop can keep iterating.
        """
        assert self._tools is not None
        timeout = self._limits.tool_timeout_s
        # OTel span: one per dispatch, attributes for grep-in-Jaeger.
        # No-op when ``opentelemetry-api`` isn't installed — see
        # :mod:`core.observability`.
        with _tracer.start_as_current_span("chat.tool_dispatch") as span:
            span.set_attribute("tool.name", tc.name)
            span.set_attribute("tool.call_id", tc.id)
            result = await self._run_tool_with_timeout(tc, abort=abort, timeout=timeout)
            span.set_attribute("tool.is_error", bool(result.is_error))
            return result

    async def _run_tool_with_timeout(
        self,
        tc: ToolCall,
        *,
        abort: AbortContext | None,
        timeout: float,
    ) -> ToolResult:
        """Body of :meth:`_dispatch_tool_with_timeout` — extracted so the
        span wrapper stays a single function and the timeout/abort race
        logic is testable in isolation."""
        assert self._tools is not None
        task = asyncio.create_task(self._tools.dispatch(tc))
        try:
            if abort is not None:
                # Race the dispatch task against the abort event so a fast
                # abort doesn't have to wait the full timeout.
                abort_task = asyncio.create_task(abort.wait())
                done, _pending = await asyncio.wait(
                    {task, abort_task},
                    timeout=timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                abort_task.cancel()
                if task in done:
                    return task.result()
                # Either timeout or abort fired first.
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
                if abort.aborted:
                    return ToolResult(
                        content=f"tool {tc.name!r} cancelled by client abort",
                        is_error=True,
                    )
                return ToolResult(
                    content=f"tool {tc.name!r} timed out after {timeout:.1f}s",
                    is_error=True,
                )
            try:
                return await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
            except asyncio.TimeoutError:  # 3.10: distinct class; 3.11+: alias of builtin
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
                return ToolResult(
                    content=f"tool {tc.name!r} timed out after {timeout:.1f}s",
                    is_error=True,
                )
        except Exception as exc:
            logger.exception("dispatch_tool_with_timeout failed unexpectedly")
            return ToolResult(
                content=f"internal error dispatching {tc.name!r}: {exc}",
                is_error=True,
            )

    async def _fit_to_budget(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        """Trim or summarize ``messages`` to fit ``self._token_budget``.

        Escalation ladder:

        * No tokenizer wired → return ``messages`` untouched (legacy path,
          relies on the LLM provider rejecting over-long input).
        * Tokenizer but no budget → also untouched (caller wants counting
          available but no enforcement).
        * Tokenizer + budget but no summarizer → :func:`trim_to_budget`
          drops oldest non-system turns.
        * Tokenizer + budget + summarizer → :meth:`HistorySummarizer.compress`
          collapses old turns into a summary, then falls back to trimming
          if the summary itself overflows.
        """
        if self._tokenizer is None or self._token_budget is None:
            return messages
        if self._summarizer is not None:
            return await self._summarizer.compress(messages, budget=self._token_budget)
        return trim_to_budget(messages, tokenizer=self._tokenizer, budget=self._token_budget)

    async def _load_history(self, session_id: str) -> tuple[list[ChatMessage], Event | None]:
        try:
            return await self._memory.get(session_id), None
        except Exception as exc:
            return [], {
                "type": "error",
                "code": "memory_read_failed",
                "message": str(exc),
            }

    async def _retrieve_for_turn(
        self,
        user_text: str,
        *,
        use_rag: bool,
        top_k: int,
        abort: AbortContext | None,
    ) -> tuple[list[KnowledgeHit], Event | None]:
        if not use_rag or self._kb is None:
            return [], None
        if abort is not None and abort.aborted:
            return [], _aborted_event()
        try:
            hits = await self._kb.search(user_text, top_k=top_k)
        except Exception as exc:
            return [], {
                "type": "error",
                "code": "retrieval_failed",
                "message": str(exc),
            }
        return hits, {
            "type": "retrieval",
            "hits": [
                {
                    "document_id": getattr(h, "document_id", None),
                    "chunk_id": getattr(h, "chunk_id", None),
                    "title": h.title,
                    "content": h.content,
                    "score": h.score,
                    "source": h.source,
                }
                for h in hits
            ],
        }

    async def _load_user_memories(self) -> list[UserMemoryEntry]:
        if self._user_memory is None:
            return []
        try:
            return await self._user_memory.recent(limit=10)
        except Exception as exc:
            logger.warning("user_memory.recent() failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def aclose(self) -> None:
        """Close the underlying LLM client."""
        for task in tuple(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()
        await self._llm.aclose()

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------
    async def new_session(self) -> str:
        return await self._memory.new_session()

    async def _maybe_generate_title(
        self,
        session_id: str,
        messages: list[ChatMessage],
        *,
        model: str | None,
    ) -> None:
        """Generate a short title for ``session_id`` if it has none yet.

        Soft failure on every step: this runs as a fire-and-forget task and
        must not raise into the asyncio task queue. The session is left
        with its preview-based fallback (see :mod:`core.titles`) on error.
        """
        from service.chat.titles import generate_llm_title

        try:
            existing = await self._memory.get_title(session_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("auto-title: get_title failed: %s", exc)
            return
        if existing:
            return  # respect any user-set or pre-existing title.

        try:
            title = await generate_llm_title(messages, self._llm, model=model)
        except Exception as exc:
            logger.info("auto-title: generation failed (non-fatal): %s", exc)
            return

        try:
            await self._memory.set_title(session_id, title)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("auto-title: set_title failed: %s", exc)

    # ------------------------------------------------------------------
    # Core ReAct loop
    # ------------------------------------------------------------------
    async def generate(
        self,
        session_id: str,
        user_text: str,
        *,
        use_rag: bool = False,
        top_k: int = 4,
        use_tools: bool = True,
        max_steps: int | None = None,
        abort: AbortContext | None = None,
        model: str | None = None,
        persist_user: bool = True,
        think: ThinkingMode | None = None,
        auto_web_search: bool | Literal["auto", "always", "off"] = "auto",
    ) -> AsyncIterator[Event]:
        """Stream the full reply loop as UI-facing events.

        ``abort`` is polled before each ``yield`` and before each tool
        dispatch. A set abort surfaces ``{"type": "error", "code": "ABORTED"}``
        and returns; the assistant/tool turns generated so far in the
        *current* iteration are dropped (persisting half a step would let
        later turns "see" a truncated trace).

        ``model`` overrides the LLM client's default for this whole loop.

        ``use_tools=False`` runs a single LLM call (legacy linear mode) even
        when a registry is attached — useful for "raw chat" tests.

        ``auto_web_search`` controls the pre-answer web-search policy:
        ``"auto"`` searches only for freshness / official-doc / research-style
        prompts, ``"always"`` searches every turn, and ``"off"`` disables the
        pre-answer search. Boolean values map to always/off for compatibility.

        Side-effects: the ``user`` message is persisted *before* the loop so
        the user's question survives a mid-loop crash. Each assistant /
        tool result message is persisted as it lands.
        """

        started = time.monotonic()

        # Resolve the effective per-call limits: per-call ``max_steps`` may
        # shrink ``self._limits.max_steps`` but never extend it. Other
        # limits are construction-time only.
        effective_max_steps = (
            min(max_steps, self._limits.max_steps)
            if max_steps is not None
            else self._limits.max_steps
        )
        effective_top_k = max(1, min(top_k, self._limits.max_top_k))

        if abort is not None and abort.aborted:
            yield _aborted_event()
            return

        # 0. Load prior history.
        history, history_error = await self._load_history(session_id)
        if history_error is not None:
            yield history_error
            return

        # 1. Optional retrieval (one-shot, before the loop). Emit the
        # ``retrieval`` event for the UI; the hit list itself goes into
        # the prompt prelude via :class:`PromptBuilder` below.
        if think is not False:
            yield {"type": "thought", "text": "Thinking through the request"}
        if use_rag and self._kb is not None:
            yield {"type": "thought", "text": "Searching local knowledge base"}
        hits, retrieval_event = await self._retrieve_for_turn(
            user_text,
            use_rag=use_rag,
            top_k=effective_top_k,
            abort=abort,
        )
        turn_sources = _sources_from_hits(hits)
        if retrieval_event is not None:
            yield retrieval_event
            if retrieval_event.get("type") == "error":
                return

        # 2. Pull long-term user memories (#16). Soft failure: a broken DB
        # connection here must not block the reply path.
        memories = await self._load_user_memories()

        # 3. Persist the user turn immediately so a mid-loop failure doesn't
        # lose the question. ``persist_user=False`` skips this — the
        # regenerate / continue-from-history paths rely on a user
        # message that's already in the transcript (an assistant reply
        # was either deleted or never produced).
        user_msg = ChatMessage(role="user", content=user_text)
        if persist_user:
            try:
                await self._memory.append(session_id, user_msg)
            except Exception as exc:
                yield {
                    "type": "error",
                    "code": "memory_write_failed",
                    "message": str(exc),
                }
                return

        # 4. ReAct loop.
        # Prompt order (oldest → newest):
        #   <system prelude> + <prior chat history> + <user question>
        # ``system prelude`` is composed by :class:`PromptBuilder` from the
        # persona system prompt + user memories + retrieval hits. Neither
        # block is persisted to chat memory — all three are regenerated per
        # turn from fresh sources.
        prelude = self._prompt_builder.build(
            system_override=self._system_prompt,
            memories=memories or None,
            hits=hits or None,
        )
        # When we *did* persist the user msg above, ``history`` was
        # loaded before the persist so ``user_msg`` is not yet inside
        # it — we append it explicitly. When ``persist_user=False`` the
        # caller has guaranteed ``history`` already ends in this user
        # turn, so duplicating would double-count.
        messages: list[ChatMessage] = (
            [*prelude, *history, user_msg] if persist_user else [*prelude, *history]
        )
        usage: dict[str, Any] | None = None
        tools_for_call: list[ToolSpec] | None = None
        if use_tools and self._tools is not None and len(self._tools) > 0:
            tools_for_call = self._tools.as_specs()
        executed_tool_keys: set[str] = set()
        executed_tool_counts: dict[str, int] = {}

        if (
            tools_for_call
            and self._tools is not None
            and "web_search" in self._tools
            and _should_auto_web_search(user_text, mode=auto_web_search, has_local_hits=bool(hits))
        ):
            tc = ToolCall(
                id=f"call_auto_web_{uuid.uuid4().hex[:12]}",
                name="web_search",
                arguments={"query": user_text, "limit": 5},
            )
            executed_tool_keys.add(_tool_call_key(tc))
            yield {"type": "thought", "text": "Searching web"}
            yield {
                "type": "tool_call",
                "tool_call_id": tc.id,
                "tool_name": tc.name,
                "arguments": tc.arguments,
            }
            result = await self._dispatch_tool_with_timeout(tc, abort=abort)
            executed_tool_counts[tc.name] = executed_tool_counts.get(tc.name, 0) + 1
            new_sources = _sources_from_tool_result(result, start_rank=len(turn_sources) + 1)
            if new_sources:
                turn_sources.extend(new_sources)
            yield {
                "type": "tool_result",
                "tool_call_id": tc.id,
                "tool_name": tc.name,
                "content": result.content,
                "is_error": result.is_error,
            }
            messages.append(ChatMessage(role="assistant", content="", tool_calls=(tc,)))
            messages.append(
                ChatMessage(
                    role="tool",
                    content=result.content,
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                )
            )

        for _ in range(effective_max_steps):
            if abort is not None and abort.aborted:
                yield _aborted_event()
                return

            # Context-window management: summarize / trim before each LLM
            # call so a long-running ReAct loop with tool results doesn't
            # silently overflow the model's window. ``messages`` is rebound
            # to the compressed copy; the persisted memory is untouched.
            messages_for_call = await self._fit_to_budget(messages)

            collected_text: list[str] = []
            collected_thinking: list[str] = []
            collected_tool_calls: list[ToolCall] = []
            think_filter = _ThinkTagStreamFilter()

            try:
                with _tracer.start_as_current_span("chat.llm_stream") as llm_span:
                    llm_span.set_attribute(
                        "llm.model", str(model or getattr(self._llm, "chat_model", "?"))
                    )
                    llm_span.set_attribute("llm.message_count", len(messages_for_call))
                    if tools_for_call:
                        llm_span.set_attribute("llm.tool_count", len(tools_for_call))
                    async for chunk in self._llm.chat_stream(
                        messages_for_call,
                        model=model,
                        tools=tools_for_call,
                        think=think,
                    ):
                        if abort is not None and abort.aborted:
                            yield _aborted_event()
                            return
                        if chunk.thinking:
                            collected_thinking.append(chunk.thinking)
                            yield {"type": "thought", "text": chunk.thinking}
                        if chunk.delta:
                            for kind, text in think_filter.feed(chunk.delta):
                                if kind == "thought":
                                    yield {"type": "thought", "text": text}
                                elif text:
                                    collected_text.append(text)
                                    yield {"type": "token", "delta": text}
                        if chunk.tool_calls:
                            collected_tool_calls.extend(chunk.tool_calls)
                        if chunk.done and chunk.usage:
                            usage = dict(chunk.usage)
                    for kind, text in think_filter.flush():
                        if kind == "thought":
                            yield {"type": "thought", "text": text}
                        elif text:
                            collected_text.append(text)
                            yield {"type": "token", "delta": text}
            except LLMError as exc:
                yield {
                    "type": "error",
                    "code": "llm_error",
                    "message": str(exc),
                }
                return
            except Exception as exc:
                yield {
                    "type": "error",
                    "code": "unexpected",
                    "message": f"{type(exc).__name__}: {exc}",
                }
                return

            assistant_text = "".join(collected_text)
            if not collected_tool_calls and not assistant_text.strip():
                assistant_text = _empty_answer_fallback(turn_sources)
                yield {"type": "token", "delta": assistant_text}
            assistant_msg = ChatMessage(
                role="assistant",
                content=assistant_text,
                thinking="".join(collected_thinking),
                tool_calls=tuple(collected_tool_calls),
                sources=tuple(turn_sources),
            )
            try:
                await self._memory.append(session_id, assistant_msg)
            except Exception as exc:
                yield {
                    "type": "error",
                    "code": "memory_write_failed",
                    "message": str(exc),
                }
                return
            messages.append(assistant_msg)

            # No tool calls → loop terminates on this assistant turn.
            if not collected_tool_calls:
                break

            # Cap the number of dispatches per step. A model that requests
            # 100 tool calls at once is almost certainly stuck in a loop;
            # we keep the first N and surface a warning result for the rest
            # so the model can see "you asked for too many" and self-correct.
            cap = self._limits.max_tool_calls_per_step
            if len(collected_tool_calls) > cap:
                logger.warning(
                    "model emitted %d tool calls in one step; capping at %d",
                    len(collected_tool_calls),
                    cap,
                )

            # Dispatch tool calls in order.
            assert self._tools is not None  # guaranteed by tools_for_call check
            for idx, tc in enumerate(collected_tool_calls):
                if abort is not None and abort.aborted:
                    yield _aborted_event()
                    return
                yield {
                    "type": "thought",
                    "text": f"Running tool: {tc.name}",
                }
                yield {
                    "type": "tool_call",
                    "tool_call_id": tc.id,
                    "tool_name": tc.name,
                    "arguments": tc.arguments,
                }
                tool_key = _tool_call_key(tc)
                tool_limit = _tool_turn_limit(tc.name)
                if idx >= cap:
                    # Past the per-step cap — return a synthetic error
                    # result rather than executing the tool.
                    result = ToolResult(
                        content=(
                            f"too many tool calls in one step (limit={cap}); "
                            f"this call ({tc.name}) was not executed"
                        ),
                        is_error=True,
                    )
                elif tool_limit is not None and executed_tool_counts.get(tc.name, 0) >= tool_limit:
                    result = ToolResult(
                        content=(
                            f"{tc.name} call skipped: per-turn limit={tool_limit}. "
                            "Use the tool results already present in this conversation and produce "
                            "the final answer now."
                        ),
                        is_error=False,
                    )
                elif tool_key in executed_tool_keys:
                    result = ToolResult(
                        content=(
                            f"duplicate tool call skipped: {tc.name}. "
                            "This exact tool call already ran in this turn; use the previous "
                            "tool result in the conversation and produce the final answer now."
                        ),
                        is_error=False,
                    )
                else:
                    executed_tool_keys.add(tool_key)
                    result = await self._dispatch_tool_with_timeout(tc, abort=abort)
                    executed_tool_counts[tc.name] = executed_tool_counts.get(tc.name, 0) + 1
                new_sources = _sources_from_tool_result(result, start_rank=len(turn_sources) + 1)
                if new_sources:
                    turn_sources.extend(new_sources)
                yield {
                    "type": "tool_result",
                    "tool_call_id": tc.id,
                    "tool_name": tc.name,
                    "content": result.content,
                    "is_error": result.is_error,
                }
                tool_msg = ChatMessage(
                    role="tool",
                    content=result.content,
                    tool_call_id=tc.id,
                    tool_name=tc.name,
                )
                try:
                    await self._memory.append(session_id, tool_msg)
                except Exception as exc:
                    yield {
                        "type": "error",
                        "code": "memory_write_failed",
                        "message": str(exc),
                    }
                    return
                messages.append(tool_msg)
            # ...next loop iteration: re-invoke the LLM with tool results
        else:
            # Loop exhausted without producing a tool-free assistant turn. Do one
            # final synthesis call with tools disabled so the user gets an answer
            # instead of a bare "agent exceeded N reasoning steps" failure.
            yield {
                "type": "thought",
                "text": "Tool step limit reached; synthesizing from collected results",
            }
            messages.append(
                ChatMessage(
                    role="system",
                    content=(
                        "Stop calling tools. Use the existing tool results and sources above to "
                        "produce the final answer now. If evidence is insufficient, say so plainly."
                    ),
                )
            )
            messages_for_call = await self._fit_to_budget(messages)
            final_text: list[str] = []
            final_thinking: list[str] = []
            think_filter = _ThinkTagStreamFilter()
            try:
                async for chunk in self._llm.chat_stream(
                    messages_for_call,
                    model=model,
                    tools=None,
                    think=think,
                ):
                    if abort is not None and abort.aborted:
                        yield _aborted_event()
                        return
                    if chunk.thinking:
                        final_thinking.append(chunk.thinking)
                        yield {"type": "thought", "text": chunk.thinking}
                    if chunk.delta:
                        for kind, text in think_filter.feed(chunk.delta):
                            if kind == "thought":
                                yield {"type": "thought", "text": text}
                            elif text:
                                final_text.append(text)
                                yield {"type": "token", "delta": text}
                    if chunk.done and chunk.usage:
                        usage = dict(chunk.usage)
                for kind, text in think_filter.flush():
                    if kind == "thought":
                        yield {"type": "thought", "text": text}
                    elif text:
                        final_text.append(text)
                        yield {"type": "token", "delta": text}
            except LLMError as exc:
                yield {
                    "type": "error",
                    "code": "llm_error",
                    "message": str(exc),
                }
                return
            except Exception as exc:
                yield {
                    "type": "error",
                    "code": "unexpected",
                    "message": f"{type(exc).__name__}: {exc}",
                }
                return

            final_answer = "".join(final_text)
            if not final_answer.strip():
                final_answer = _empty_answer_fallback(turn_sources)
                yield {"type": "token", "delta": final_answer}
            assistant_msg = ChatMessage(
                role="assistant",
                content=final_answer,
                thinking="".join(final_thinking),
                sources=tuple(turn_sources),
            )
            try:
                await self._memory.append(session_id, assistant_msg)
            except Exception as exc:
                yield {
                    "type": "error",
                    "code": "memory_write_failed",
                    "message": str(exc),
                }
                return
            messages.append(assistant_msg)

        # 4. Fact extraction (post-success, fire-and-forget semantics —
        # failure here must not surface as an error to the user). We extract
        # only from the messages newly produced in *this* turn so a long
        # history doesn't re-extract the same facts repeatedly.
        if self._fact_extractor is not None and self._user_memory is not None:
            new_turn = messages[len(history) :]
            try:
                facts = await self._fact_extractor.extract(new_turn)
            except Exception as exc:
                logger.warning("fact extraction failed: %s", exc)
                facts = []
            source_uuid = _maybe_uuid(session_id)
            for fact in facts:
                try:
                    await self._user_memory.add(fact, source_session_id=source_uuid)
                except Exception as exc:
                    logger.warning("user_memory.add(%r) failed: %s", fact, exc)

        # 5. Usage accounting (#22). Done on the success path only — an
        # errored / aborted turn doesn't accumulate cost.
        if self._usage is not None:
            # Count tool calls actually executed across the whole turn.
            executed_tool_msgs = sum(1 for m in messages[len(history) :] if m.role == "tool")
            self._usage.record_usage_dict(
                usage,
                model=model or getattr(self._llm, "chat_model", None),
                tool_calls=executed_tool_msgs,
            )

        # 6. Auto-title (fire-and-forget). Only on the first assistant turn
        # of a session that does not already have a user-set title. Runs in
        # the background so a slow / failing title call never blocks the
        # ``done`` event.
        if not any(m.role == "assistant" for m in history):
            title_task = asyncio.create_task(
                self._maybe_generate_title(session_id, messages, model=model)
            )
            self._background_tasks.add(title_task)
            title_task.add_done_callback(self._background_tasks.discard)

        # 7. Terminator.
        duration_ms = int((time.monotonic() - started) * 1000)
        effective_model = model or getattr(self._llm, "chat_model", None)
        done: Event = {"type": "done", "duration_ms": duration_ms}
        if usage is not None:
            done["usage"] = usage
        if effective_model:
            done["model"] = effective_model
        if turn_sources:
            done["sources"] = turn_sources
        yield done

    # ------------------------------------------------------------------
    # Aggregated (non-streaming) helper
    # ------------------------------------------------------------------
    async def generate_full(
        self,
        session_id: str,
        user_text: str,
        *,
        use_rag: bool = False,
        top_k: int = 4,
        use_tools: bool = True,
        max_steps: int | None = None,
        model: str | None = None,
        think: ThinkingMode | None = None,
        auto_web_search: bool | Literal["auto", "always", "off"] = "auto",
    ) -> dict[str, Any]:
        """Run :meth:`generate` to completion and return an aggregated result.

        Shape::

            {
                "content": "...",          # concatenated assistant text
                "hits":    [...] | None,   # only when RAG fired
                "usage":   {...} | None,
                "duration_ms": int | None,
                "tool_calls":  [...] | None,   # appearance order
                "tool_results":[...] | None,
                "error":   {"code": "...", "message": "..."} | None,
            }

        Used by the REST ``POST /chat/messages`` route so both the streaming
        and non-streaming surfaces share one generator (avoids drift between
        SSE and REST semantics). Tool activity is folded into ``tool_calls``
        / ``tool_results`` so non-streaming clients still see the full trace.
        """

        content_parts: list[str] = []
        hits: list[dict[str, Any]] | None = None
        usage: dict[str, Any] | None = None
        duration_ms: int | None = None
        sources: list[dict[str, Any]] | None = None
        tool_calls: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        error: dict[str, str] | None = None

        async for event in self.generate(
            session_id,
            user_text,
            use_rag=use_rag,
            top_k=top_k,
            use_tools=use_tools,
            max_steps=max_steps,
            model=model,
            think=think,
            auto_web_search=auto_web_search,
        ):
            etype = event.get("type")
            if etype == "token":
                delta = event.get("delta")
                if isinstance(delta, str):
                    content_parts.append(delta)
            elif etype == "retrieval":
                raw_hits = event.get("hits")
                if isinstance(raw_hits, list):
                    hits = list(raw_hits)
            elif etype == "tool_call":
                tool_calls.append(
                    {
                        "tool_call_id": event.get("tool_call_id"),
                        "tool_name": event.get("tool_name"),
                        "arguments": event.get("arguments"),
                    }
                )
            elif etype == "tool_result":
                tool_results.append(
                    {
                        "tool_call_id": event.get("tool_call_id"),
                        "tool_name": event.get("tool_name"),
                        "content": event.get("content"),
                        "is_error": event.get("is_error"),
                    }
                )
            elif etype == "done":
                raw_usage = event.get("usage")
                if isinstance(raw_usage, dict):
                    usage = dict(raw_usage)
                raw_duration = event.get("duration_ms")
                if isinstance(raw_duration, int):
                    duration_ms = raw_duration
                raw_sources = event.get("sources")
                if isinstance(raw_sources, list):
                    sources = [s for s in raw_sources if isinstance(s, dict)]
            elif etype == "error":
                error = {
                    "code": str(event.get("code", "UNKNOWN")),
                    "message": str(event.get("message", "")),
                }
                break

        return {
            "content": "".join(content_parts),
            "hits": hits,
            "usage": usage,
            "duration_ms": duration_ms,
            "sources": sources,
            "tool_calls": tool_calls or None,
            "tool_results": tool_results or None,
            "error": error,
        }


class _ThinkTagStreamFilter:
    """Split streamed text into answer tokens and ``<think>`` thought text."""

    _OPEN: ClassVar[str] = "<think>"
    _CLOSE: ClassVar[str] = "</think>"

    def __init__(self) -> None:
        self._buffer: str = ""
        self._in_think: bool = False

    def feed(self, text: str) -> list[tuple[str, str]]:
        self._buffer += text
        return self._drain(final=False)

    def flush(self) -> list[tuple[str, str]]:
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        while self._buffer:
            if self._in_think:
                idx = self._find(self._CLOSE)
                if idx >= 0:
                    self._emit(out, "thought", self._buffer[:idx])
                    self._buffer = self._buffer[idx + len(self._CLOSE) :]
                    self._in_think = False
                    continue
                if final:
                    self._emit(out, "thought", self._buffer)
                    self._buffer = ""
                break

            idx = self._find(self._OPEN)
            if idx >= 0:
                self._emit(out, "token", self._buffer[:idx])
                self._buffer = self._buffer[idx + len(self._OPEN) :]
                self._in_think = True
                continue
            keep = 0 if final else len(self._OPEN) - 1
            safe_len = max(0, len(self._buffer) - keep)
            if safe_len:
                self._emit(out, "token", self._buffer[:safe_len])
                self._buffer = self._buffer[safe_len:]
            break
        if final:
            self._buffer = ""
        return out

    def _find(self, tag: str) -> int:
        return self._buffer.lower().find(tag)

    @staticmethod
    def _emit(out: list[tuple[str, str]], kind: str, text: str) -> None:
        if text:
            out.append((kind, text))


def _aborted_event() -> Event:
    return {
        "type": "error",
        "code": "ABORTED",
        "message": "client aborted the stream",
    }


def _empty_answer_fallback(sources: list[dict[str, Any]]) -> str:
    if sources:
        return (
            "I gathered supporting sources but the model did not produce a final answer. "
            "Please retry, or open the sources panel to inspect the collected evidence."
        )
    return "The model stopped before producing a final answer. Please retry."


def _tool_call_key(call: ToolCall) -> str:
    try:
        args = json.dumps(call.arguments, sort_keys=True, ensure_ascii=False, default=str)
    except TypeError:
        args = repr(call.arguments)
    return f"{call.name}:{args}"


def _tool_turn_limit(name: str) -> int | None:
    if name == "web_search":
        return 1
    if name == "web_fetch":
        return 2
    return None


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


def _should_auto_web_search(
    text: str,
    *,
    mode: bool | Literal["auto", "always", "off"],
    has_local_hits: bool,
) -> bool:
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


def _sources_from_hits(hits: list[KnowledgeHit]) -> list[dict[str, Any]]:
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


def _sources_from_tool_result(result: ToolResult, *, start_rank: int) -> list[dict[str, Any]]:
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


def _maybe_uuid(s: str) -> uuid.UUID | None:
    """Try to parse ``s`` as a UUID; return ``None`` on failure.

    Used to convert the opaque ``session_id`` passed to :meth:`generate`
    into a foreign key for ``user_memories.source_session_id``. File-backed
    sessions use short hex tokens that won't parse as UUIDs and degrade to
    ``None`` here, which is the intended behaviour (no FK to attach).
    """
    try:
        return uuid.UUID(s)
    except (ValueError, TypeError):
        return None
