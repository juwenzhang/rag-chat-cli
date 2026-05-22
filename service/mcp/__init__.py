"""Model Context Protocol client (#21 P5.2).

Public surface:

* :class:`MCPStdioClient` — JSON-RPC over a subprocess's stdin/stdout.
  Use to talk to any MCP server published via ``uvx`` / ``npx``.
* :class:`MCPToolInfo` — one remote tool's metadata as returned by
  ``tools/list``.
* :class:`McpTool` — adapts one :class:`MCPToolInfo` to the local
  :class:`service.tools.Tool` Protocol so it can be registered in a
  :class:`~service.tools.ToolRegistry` alongside in-process tools.
* :func:`wrap_as_tools` — bulk adapter.
* :class:`MCPError` — raised on transport / protocol failures.

Typical wiring (e.g. inside ``tui/chat_app.py``)::

    from service.mcp import MCPStdioClient, wrap_as_tools
    from service.tools import ToolRegistry

    fetch = MCPStdioClient(["uvx", "mcp-server-fetch"])
    await fetch.start()
    registry = ToolRegistry()
    for tool in wrap_as_tools(fetch, await fetch.list_tools(), namespace="fetch"):
        registry.register(tool)

    # ... use registry with ChatService ...
    # at shutdown:
    await fetch.aclose()
"""

from __future__ import annotations

from service.mcp.adapter import McpTool, wrap_as_tools
from service.mcp.client import MCPError, MCPStdioClient, MCPToolInfo

__all__ = [
    "MCPError",
    "MCPStdioClient",
    "MCPToolInfo",
    "McpTool",
    "wrap_as_tools",
]
