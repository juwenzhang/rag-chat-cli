"""Tool execution primitives — :class:`Tool` Protocol + :class:`ToolResult`.

This is the boundary between the LLM's intent (a :class:`core.llm.client.ToolCall`)
and the host-side side-effects that fulfill it. The split is intentional:

* :mod:`core.llm.client` owns the LLM-facing shapes (``ToolSpec``, ``ToolCall``).
* :mod:`core.tools` owns the execution-facing shapes (``Tool``, ``ToolResult``,
  ``ToolError``, ``ToolRegistry``).

Concrete tools live next to feature code (or in :mod:`core.tools.builtin` once
that exists). The :class:`ToolRegistry` in :mod:`core.tools.registry` is what
the ReAct loop in :mod:`core.chat_service` will consult.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from core.llm.client import ToolSpec

__all__ = [
    "FunctionTool",
    "Tool",
    "ToolError",
    "ToolResult",
    "tool_to_spec",
]


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Result of executing one tool call.

    ``content`` is what gets fed back to the LLM as the ``role="tool"``
    message body — should be a short, LLM-friendly string (typically a
    JSON-encoded payload, or natural-language summary).

    ``is_error=True`` tells the orchestrator the tool failed *recoverably*;
    the LLM can be re-prompted to retry or change approach. Unhandled
    exceptions inside :meth:`Tool.call` are caught by
    :meth:`ToolRegistry.dispatch` and surfaced as ``is_error=True`` too.

    ``metadata`` is for the UI / observability layer (citations, attribution,
    timing) and is NOT sent to the LLM.
    """

    content: str
    is_error: bool = False
    metadata: dict[str, Any] | None = None


class ToolError(Exception):
    """Raised inside :meth:`Tool.call` to signal a recoverable failure.

    The registry catches this and turns the message into a
    ``ToolResult(content=str(exc), is_error=True)`` that the LLM can see.
    """


@runtime_checkable
class Tool(Protocol):
    """Contract for one tool the LLM can invoke.

    Tools are expected to be cheap to construct (heavy work lives in
    :meth:`call`). They may close over a connection pool / HTTP client /
    db session — in which case their owning ``ToolRegistry`` is responsible
    for lifecycle. There is no ``aclose`` on the Protocol; tools that need
    teardown should expose it themselves and be paired with an exit stack.
    """

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for ``call``'s arguments dict."""
        ...

    async def call(self, arguments: dict[str, Any]) -> ToolResult:
        """Execute the tool.

        ``arguments`` is the JSON-decoded payload extracted from
        :class:`core.llm.client.ToolCall`. Implementations should
        validate it and raise :class:`ToolError` on bad input rather
        than letting a generic ``KeyError`` / ``TypeError`` escape.
        """
        ...


def tool_to_spec(tool: Tool) -> ToolSpec:
    """Project a :class:`Tool` into a :class:`ToolSpec` for offer to the LLM.

    Lives as a free function (not a Protocol method) so :class:`Tool` keeps
    its single concern of *executing*; spec projection is a render step.
    """
    return ToolSpec(
        name=tool.name,
        description=tool.description,
        parameters=tool.parameters,
    )


class FunctionTool:
    """Adapter that turns a plain async function into a :class:`Tool`.

    Use this for stateless tools where a full class feels heavy::

        async def _echo(args: dict) -> ToolResult:
            return ToolResult(content=str(args.get("text", "")))

        registry.register(FunctionTool(
            name="echo",
            description="Echo the text argument back as-is.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            fn=_echo,
        ))
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        fn: Callable[[dict[str, Any]], Awaitable[ToolResult]],
    ) -> None:
        self._name = name
        self._description = description
        self._parameters = parameters
        self._fn = fn

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def call(self, arguments: dict[str, Any]) -> ToolResult:
        return await self._fn(arguments)
