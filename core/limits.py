"""Resource limits for the ReAct loop (#19 P4.2).

Caps that protect against pathological model behaviour:

* A model that emits an unbounded sequence of tool calls (caught by
  ``max_steps`` on the outer loop and ``max_tool_calls_per_step`` on
  each iteration).
* A tool that hangs indefinitely (``tool_timeout_s`` wraps
  :meth:`core.tools.Tool.call` in :func:`asyncio.wait_for`).
* A model that asks for retrieval on every turn with huge ``top_k``
  (``max_top_k`` clamps the value passed in by callers).

All limits have **soft** semantics: hitting a cap surfaces a regular
``error`` event, not a crash; the user / orchestrator can retry. The
defaults are deliberately generous — tighten in production via the
construction parameter on :class:`~core.chat_service.ChatService`.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["DEFAULT_LIMITS", "ResourceLimits"]


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Soft caps applied per :meth:`ChatService.generate` invocation.

    Construct with the named-field syntax to override only the limits you
    care about::

        limits = ResourceLimits(tool_timeout_s=5.0, max_tool_calls_per_step=4)

    ``max_steps`` here is the *ceiling*; the per-call ``max_steps``
    argument to :meth:`ChatService.generate` may shrink it further but
    not extend it.
    """

    max_steps: int = 5
    max_tool_calls_per_step: int = 8
    tool_timeout_s: float = 30.0
    max_top_k: int = 20

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError(f"max_steps must be >= 1, got {self.max_steps}")
        if self.max_tool_calls_per_step < 1:
            raise ValueError(
                f"max_tool_calls_per_step must be >= 1, got {self.max_tool_calls_per_step}"
            )
        if self.tool_timeout_s <= 0:
            raise ValueError(f"tool_timeout_s must be > 0, got {self.tool_timeout_s}")
        if self.max_top_k < 1:
            raise ValueError(f"max_top_k must be >= 1, got {self.max_top_k}")


#: Module-level default — used as the construction default on
#: :class:`~core.chat_service.ChatService` when no overrides are given.
DEFAULT_LIMITS = ResourceLimits()
