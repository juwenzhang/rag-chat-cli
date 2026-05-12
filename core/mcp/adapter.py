"""Adapt an :class:`MCPStdioClient`'s remote tools into in-process :class:`Tool` s.

After ``client.start()`` and ``client.list_tools()``, call
:func:`wrap_as_tools` to produce a list of :class:`McpTool` objects that
satisfy :class:`core.tools.Tool` — they can then be ``ToolRegistry.register``'ed
right next to local :class:`~core.tools.FunctionTool` s. The ReAct loop in
:class:`~core.chat_service.ChatService` doesn't know or care which side of
the IPC boundary a tool actually lives on.

Naming collisions: if two MCP servers expose the same ``name``, the second
``ToolRegistry.register`` call raises (by design — silent shadowing is the
worst bug). The caller is expected to disambiguate via ``namespace`` —
either by passing a per-server prefix to :func:`wrap_as_tools` or by
using a dedicated :class:`ToolRegistry` per server.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from core.tools import ToolError, ToolResult

if TYPE_CHECKING:
    from core.mcp.client import MCPStdioClient, MCPToolInfo

__all__ = ["McpTool", "wrap_as_tools"]


class McpTool:
    """One remote MCP tool, exposed as a local :class:`core.tools.Tool`.

    Holds a reference back to the owning :class:`MCPStdioClient` so each
    ``call(args)`` becomes one ``tools/call`` JSON-RPC round trip. We do
    NOT spawn one subprocess per tool — they all share the parent client.
    """

    def __init__(
        self,
        *,
        info: MCPToolInfo,
        client: MCPStdioClient,
        namespace: str | None = None,
    ) -> None:
        self._info = info
        self._client = client
        # Optional prefix so two MCP servers can expose the same upstream
        # name without colliding in the local :class:`ToolRegistry`.
        self._namespace = namespace

    # ------------------------------------------------------------------
    # Tool Protocol
    # ------------------------------------------------------------------
    @property
    def name(self) -> str:
        if self._namespace:
            return f"{self._namespace}.{self._info.name}"
        return self._info.name

    @property
    def description(self) -> str:
        return self._info.description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._info.input_schema

    @property
    def upstream_name(self) -> str:
        """The bare name as advertised by the MCP server, without any
        local namespace prefix — what ``tools/call`` expects."""
        return self._info.name

    async def call(self, arguments: dict[str, Any]) -> ToolResult:
        """Forward to the MCP server and wrap the response.

        Any transport / JSON-RPC failure becomes ``ToolResult(is_error=True)``
        — never raise, since the :class:`ToolRegistry` already provides
        that envelope but the model behaves more sensibly if we keep the
        upstream error text intact rather than collapsing into a generic
        ``internal error`` string.
        """
        from core.mcp.client import MCPError

        try:
            text = await self._client.call_tool(self.upstream_name, arguments)
        except MCPError as exc:
            # ToolError makes the registry surface this as ``is_error=True``
            # with the original message — much more useful to the LLM than
            # ``RuntimeError`` leaking through.
            raise ToolError(str(exc)) from exc
        return ToolResult(content=text or "<empty>")


def wrap_as_tools(
    client: MCPStdioClient,
    infos: list[MCPToolInfo],
    *,
    namespace: str | None = None,
) -> list[McpTool]:
    """Wrap every entry from ``client.list_tools()`` as a local Tool.

    Pass ``namespace="brave_search"`` (for example) to prefix every tool
    name with ``brave_search.``. Useful when registering tools from
    multiple MCP servers in the same :class:`ToolRegistry`.
    """
    return [McpTool(info=info, client=client, namespace=namespace) for info in infos]


def render_arguments_for_log(arguments: dict[str, Any]) -> str:
    """Compact JSON repr used for OTel span attributes / debug logs.

    Kept here (not in :mod:`core.mcp.client`) so the client stays
    transport-only. Truncates at 200 chars to avoid blowing up
    observability budgets on tools that receive large blobs.
    """
    try:
        s = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        s = repr(arguments)
    return s if len(s) <= 200 else s[:197] + "…"
