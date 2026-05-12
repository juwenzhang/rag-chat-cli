"""Tool registry — name lookup + dispatch.

The :class:`ToolRegistry` is the seam the ReAct loop in
:class:`core.chat_service.ChatService` will use:

* :meth:`as_specs` — produces the ``tools=...`` argument for
  :meth:`core.llm.client.LLMClient.chat_stream`.
* :meth:`dispatch` — executes one :class:`core.llm.client.ToolCall` and
  returns a :class:`core.tools.base.ToolResult` (never raises; tool
  exceptions are caught and turned into ``is_error=True`` results so a
  single bad tool cannot crash the agent loop).
"""

from __future__ import annotations

import logging

from core.llm.client import ToolCall, ToolSpec
from core.tools.base import Tool, ToolError, ToolResult, tool_to_spec

__all__ = ["ToolRegistry"]

logger = logging.getLogger(__name__)


class ToolRegistry:
    """In-memory ``name → Tool`` map.

    Not thread-safe by design — the agent loop is single-task; if you need
    parallelism, wrap the registry per-request.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------
    def register(self, tool: Tool) -> None:
        """Register a tool. Raises ``ValueError`` on duplicate ``name``.

        Refusing duplicates is deliberate: silently overwriting would make
        debugging an MCP / plugin name collision very hard.
        """
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} is already registered")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Remove a tool by name. No-op if not registered."""
        self._tools.pop(name, None)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._tools

    def as_specs(self) -> list[ToolSpec]:
        """Snapshot every registered tool as a :class:`ToolSpec`.

        Returns a fresh list each call so callers may mutate it (e.g. filter
        per-conversation) without affecting the registry.
        """
        return [tool_to_spec(t) for t in self._tools.values()]

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    async def dispatch(self, call: ToolCall) -> ToolResult:
        """Execute ``call`` and return a :class:`ToolResult`.

        Never raises — every failure mode (unknown tool, ``ToolError``,
        unexpected exception) is funnelled into ``is_error=True``. This lets
        the ReAct loop treat tool execution as total: it always has a result
        to feed back to the LLM.
        """
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(
                content=(
                    f"unknown tool: {call.name!r} "
                    f"(available: {', '.join(self.names()) or '<none>'})"
                ),
                is_error=True,
            )
        try:
            return await tool.call(call.arguments)
        except ToolError as exc:
            return ToolResult(content=str(exc), is_error=True)
        except Exception as exc:
            logger.exception("tool %r raised unhandled exception", call.name)
            return ToolResult(
                content=f"internal error: {type(exc).__name__}: {exc}",
                is_error=True,
            )
