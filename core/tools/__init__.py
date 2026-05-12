"""Tool execution layer for the agent loop.

Public surface:

* :class:`Tool` — Protocol every tool implements.
* :class:`ToolResult` — return type of :meth:`Tool.call`.
* :class:`ToolError` — recoverable failure raised by a tool.
* :class:`FunctionTool` — adapter for plain async functions.
* :class:`ToolRegistry` — name lookup + dispatch.
* :func:`tool_to_spec` — project a Tool into the LLM-facing ``ToolSpec``.

The LLM-facing primitives (:class:`~core.llm.client.ToolSpec`,
:class:`~core.llm.client.ToolCall`) live in :mod:`core.llm.client`; this
module owns the execution side.
"""

from __future__ import annotations

from core.tools.base import (
    FunctionTool,
    Tool,
    ToolError,
    ToolResult,
    tool_to_spec,
)
from core.tools.registry import ToolRegistry

__all__ = [
    "FunctionTool",
    "Tool",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
    "tool_to_spec",
]
