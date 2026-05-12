"""High-level chat orchestration — ReAct loop.

:class:`ChatService` is the single seam between :mod:`app` and the rest of
:mod:`core`. It owns an :class:`~core.llm.client.LLMClient`, a
:class:`~core.memory.chat_memory.ChatMemory`, an optional retriever and an
optional :class:`~core.tools.ToolRegistry`, and exposes one async generator
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
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from core.history import HistorySummarizer
from core.knowledge.base import KnowledgeBase, KnowledgeHit
from core.limits import DEFAULT_LIMITS, ResourceLimits
from core.llm.client import ChatMessage, LLMClient, LLMError, ToolCall, ToolSpec
from core.memory.chat_memory import ChatMemory
from core.memory.user_memory import FactExtractor, UserMemoryEntry, UserMemoryStore
from core.observability import UsageAccumulator, get_tracer
from core.prompts import DEFAULT_TEMPLATES, PromptBuilder
from core.streaming.abort import AbortContext
from core.streaming.events import Event
from core.tokens import TokenBudget, Tokenizer, trim_to_budget
from core.tools import ToolRegistry, ToolResult

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
        like :meth:`~core.knowledge.local.FileKnowledgeBase.add_document`.
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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def aclose(self) -> None:
        """Close the underlying LLM client."""
        await self._llm.aclose()

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------
    async def new_session(self) -> str:
        return await self._memory.new_session()

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
        try:
            history = await self._memory.get(session_id)
        except Exception as exc:
            yield {
                "type": "error",
                "code": "memory_read_failed",
                "message": str(exc),
            }
            return

        # 1. Optional retrieval (one-shot, before the loop). Emit the
        # ``retrieval`` event for the UI; the hit list itself goes into
        # the prompt prelude via :class:`PromptBuilder` below.
        hits: list[KnowledgeHit] = []
        if use_rag and self._kb is not None:
            if abort is not None and abort.aborted:
                yield _aborted_event()
                return
            try:
                hits = await self._kb.search(user_text, top_k=effective_top_k)
            except Exception as exc:
                yield {
                    "type": "error",
                    "code": "retrieval_failed",
                    "message": str(exc),
                }
                return
            yield {
                "type": "retrieval",
                "hits": [
                    {
                        "title": h.title,
                        "content": h.content,
                        "score": h.score,
                        "source": h.source,
                    }
                    for h in hits
                ],
            }

        # 2. Pull long-term user memories (#16). Soft failure: a broken DB
        # connection here must not block the reply path.
        memories: list[UserMemoryEntry] = []
        if self._user_memory is not None:
            try:
                memories = await self._user_memory.recent(limit=10)
            except Exception as exc:
                logger.warning("user_memory.recent() failed: %s", exc)
                memories = []

        # 3. Persist the user turn immediately so a mid-loop failure doesn't
        # lose the question.
        user_msg = ChatMessage(role="user", content=user_text)
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
        messages: list[ChatMessage] = [*prelude, *history, user_msg]
        usage: dict[str, Any] | None = None
        tools_for_call: list[ToolSpec] | None = None
        if use_tools and self._tools is not None and len(self._tools) > 0:
            tools_for_call = self._tools.as_specs()

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
            collected_tool_calls: list[ToolCall] = []

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
                    ):
                        if abort is not None and abort.aborted:
                            yield _aborted_event()
                            return
                        if chunk.delta:
                            collected_text.append(chunk.delta)
                            yield {"type": "token", "delta": chunk.delta}
                        if chunk.tool_calls:
                            collected_tool_calls.extend(chunk.tool_calls)
                        if chunk.done and chunk.usage:
                            usage = dict(chunk.usage)
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
            assistant_msg = ChatMessage(
                role="assistant",
                content=assistant_text,
                tool_calls=tuple(collected_tool_calls),
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
                    len(collected_tool_calls), cap,
                )

            # Dispatch tool calls in order.
            assert self._tools is not None  # guaranteed by tools_for_call check
            for idx, tc in enumerate(collected_tool_calls):
                if abort is not None and abort.aborted:
                    yield _aborted_event()
                    return
                yield {
                    "type": "tool_call",
                    "tool_call_id": tc.id,
                    "tool_name": tc.name,
                    "arguments": tc.arguments,
                }
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
                else:
                    result = await self._dispatch_tool_with_timeout(tc, abort=abort)
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
            # Loop exhausted without producing a tool-free assistant turn.
            yield {
                "type": "error",
                "code": "max_steps_reached",
                "message": f"agent exceeded {effective_max_steps} reasoning steps",
            }
            return

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
            executed_tool_msgs = sum(
                1
                for m in messages[len(history) :]
                if m.role == "tool"
            )
            self._usage.record_usage_dict(
                usage,
                model=model or getattr(self._llm, "chat_model", None),
                tool_calls=executed_tool_msgs,
            )

        # 6. Terminator.
        duration_ms = int((time.monotonic() - started) * 1000)
        done: Event = {"type": "done", "duration_ms": duration_ms}
        if usage is not None:
            done["usage"] = usage
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
            "tool_calls": tool_calls or None,
            "tool_results": tool_results or None,
            "error": error,
        }


def _aborted_event() -> Event:
    return {
        "type": "error",
        "code": "ABORTED",
        "message": "client aborted the stream",
    }


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


