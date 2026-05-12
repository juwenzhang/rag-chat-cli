"""Observability — OTel spans (optional) + in-process usage accumulator (#22 P5.3).

Two independent layers in one module:

1. :func:`get_tracer` — returns either a real ``opentelemetry.trace.Tracer``
   if the SDK is installed, or a no-op shim otherwise. Spans are added at
   the seams in :class:`core.chat_service.ChatService` so a production
   deployment that configures an OTel exporter (Jaeger, Tempo, Honeycomb)
   gets a full per-turn trace tree for free.

2. :class:`UsageAccumulator` — pure in-process counter for tokens / tool
   calls / cost across the lifetime of a service instance. Cheap to read
   (``snapshot()`` returns a dataclass), no external dep. Useful for the
   ``/usage`` REPL command and for logging totals at shutdown.

OTel is an **optional dependency**. The shim makes ``with tracer.start_as_current_span(...)``
work even when ``opentelemetry-api`` isn't installed — so we don't force
the dep on users who don't need tracing.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, cast

__all__ = [
    "Span",
    "Tracer",
    "UsageAccumulator",
    "UsageSnapshot",
    "get_tracer",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tracer shim
# ---------------------------------------------------------------------------


class Span(Protocol):
    """Minimum span surface used by the rest of the project."""

    def set_attribute(self, key: str, value: Any) -> None: ...
    def record_exception(self, exc: BaseException) -> None: ...


class Tracer(Protocol):
    """Minimum tracer surface used by :class:`core.chat_service.ChatService`."""

    def start_as_current_span(self, name: str, /) -> Any:
        """Context-manager that yields a :class:`Span`. The return type is
        intentionally ``Any`` so both the OTel SDK's real context manager and
        our :class:`_NoopSpan` satisfy it without an extra Protocol layer."""
        ...


class _NoopSpan:
    """Span that drops every call. Returned by :class:`_NoopTracer`."""

    def set_attribute(self, key: str, value: Any) -> None:
        del key, value

    def record_exception(self, exc: BaseException) -> None:
        del exc


class _NoopTracer:
    """Tracer used when ``opentelemetry-api`` isn't installed.

    ``start_as_current_span`` returns a context manager that yields a
    :class:`_NoopSpan` and otherwise does nothing — so call-site code stays
    identical regardless of whether tracing is wired up.
    """

    @contextmanager
    def start_as_current_span(self, name: str, /) -> Iterator[_NoopSpan]:
        del name
        yield _NoopSpan()


def get_tracer(name: str) -> Tracer:
    """Return a real OTel tracer if available, else a no-op shim.

    Call once at module load (typical) or per-call (also fine — OTel
    tracer lookup is fast). ``name`` should be the dotted module path so
    spans can be filtered by component in the collector.
    """
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]

        return cast("Tracer", trace.get_tracer(name))
    except ImportError:
        return _NoopTracer()


# ---------------------------------------------------------------------------
# Usage accumulator
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    """Read-only view of the totals collected so far.

    ``cost_usd`` is best-effort: it requires the caller to plug in a
    per-1k-token price table (:meth:`UsageAccumulator.set_prices`).
    Without a price table, ``cost_usd`` stays at ``0.0``.
    """

    turns: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tool_calls: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(slots=True)
class UsageAccumulator:
    """Running totals across many :meth:`ChatService.generate` invocations.

    Thread / asyncio safety: the accumulator is *not* synchronized. Use
    one instance per service / per request scope and aggregate externally
    if needed — keeping it lock-free keeps the hot path zero-overhead.
    """

    snapshot_state: UsageSnapshot = field(default_factory=UsageSnapshot)
    _prices_per_1k: dict[str, tuple[float, float]] = field(default_factory=dict)

    def set_prices(self, model: str, *, input_per_1k: float, output_per_1k: float) -> None:
        """Register USD-per-1k-token rates for ``model``.

        Costs are accumulated using ``model`` as a key when
        :meth:`record_usage` is called — unknown models contribute zero
        cost rather than raising, so adding pricing is purely additive.
        """
        self._prices_per_1k[model] = (input_per_1k, output_per_1k)

    def record_usage(
        self,
        *,
        model: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        tool_calls: int = 0,
    ) -> None:
        """Bump the running totals after one ``generate()`` call.

        Per-provider differences:

        * Ollama → ``prompt_eval_count`` / ``eval_count``
        * OpenAI → ``prompt_tokens`` / ``completion_tokens``

        Callers should normalise into the OpenAI naming before invoking
        this method — :meth:`record_usage_dict` does that mapping.
        """
        added_cost = 0.0
        if model is not None and model in self._prices_per_1k:
            in_rate, out_rate = self._prices_per_1k[model]
            added_cost = (
                (prompt_tokens / 1000.0) * in_rate
                + (completion_tokens / 1000.0) * out_rate
            )
        self.snapshot_state = replace(
            self.snapshot_state,
            turns=self.snapshot_state.turns + 1,
            prompt_tokens=self.snapshot_state.prompt_tokens + prompt_tokens,
            completion_tokens=self.snapshot_state.completion_tokens + completion_tokens,
            tool_calls=self.snapshot_state.tool_calls + tool_calls,
            cost_usd=self.snapshot_state.cost_usd + added_cost,
        )

    def record_usage_dict(
        self,
        usage: dict[str, Any] | None,
        *,
        model: str | None = None,
        tool_calls: int = 0,
    ) -> None:
        """Accept either the OpenAI or Ollama shape and normalise to fields.

        OpenAI emits ``{prompt_tokens, completion_tokens, total_tokens}``;
        Ollama emits ``{prompt_eval_count, eval_count, …}``. Either works.
        Missing fields are treated as zero — keeps the metric honest when
        an upstream doesn't return token counts at all.
        """
        if usage is None:
            self.record_usage(model=model, tool_calls=tool_calls)
            return
        prompt = (
            usage.get("prompt_tokens")
            or usage.get("prompt_eval_count")
            or 0
        )
        completion = (
            usage.get("completion_tokens")
            or usage.get("eval_count")
            or 0
        )
        self.record_usage(
            model=model,
            prompt_tokens=int(prompt) if isinstance(prompt, (int, float)) else 0,
            completion_tokens=int(completion) if isinstance(completion, (int, float)) else 0,
            tool_calls=tool_calls,
        )

    def snapshot(self) -> UsageSnapshot:
        """Read-only point-in-time copy. Cheap to call from a UI loop."""
        return self.snapshot_state

    def reset(self) -> None:
        """Zero out everything. Prices survive (configuration, not state)."""
        self.snapshot_state = UsageSnapshot()
