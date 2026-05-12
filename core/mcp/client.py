"""Minimum-viable Model Context Protocol client (#21 P5.2).

`MCP <https://modelcontextprotocol.io/>`_ lets the agent borrow tools from
external "MCP servers" that speak JSON-RPC 2.0 over a transport — usually
stdio (subprocess with newline-delimited JSON on stdin/stdout). This module
implements **stdio transport only** for the first pass; HTTP/SSE servers
can follow the same shape with a different ``_send_line`` / ``_reader``.

Public surface:

* :class:`MCPStdioClient` — spawn a subprocess, do the ``initialize``
  handshake, expose ``list_tools()`` + ``call_tool(name, args)``.
* :func:`wrap_as_tools` (in :mod:`core.mcp.adapter`) — adapt each remote
  tool into a :class:`core.tools.Tool` so it can be registered in a
  :class:`~core.tools.ToolRegistry` alongside in-process tools.

The protocol vocabulary used here is the subset every MCP server is
required to implement — extras (``resources``, ``prompts``,
``logging``) can be added in follow-up changes without breaking this API.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
from dataclasses import dataclass
from typing import Any

__all__ = [
    "MCPError",
    "MCPStdioClient",
    "MCPToolInfo",
]

logger = logging.getLogger(__name__)


# JSON-RPC framing constants. ``CLIENT_PROTOCOL_VERSION`` is the value we
# pass during ``initialize``; the server picks any compatible version and
# echoes back ``protocolVersion`` in the response. ``2024-11-05`` is the
# stable MCP version as of early 2026 and is what nearly every public
# server in the wild supports.
_CLIENT_PROTOCOL_VERSION = "2024-11-05"
_CLIENT_INFO = {"name": "rag-ai-cli", "version": "1.4"}
_INIT_TIMEOUT_S = 10.0
_DEFAULT_CALL_TIMEOUT_S = 30.0


class MCPError(Exception):
    """Raised on transport failure, malformed JSON-RPC frames, or remote
    error responses. Callers at the :class:`~core.tools.ToolRegistry`
    seam convert this to ``ToolResult(is_error=True)``."""


@dataclass(frozen=True, slots=True)
class MCPToolInfo:
    """One remote tool as advertised by ``tools/list``."""

    name: str
    description: str
    input_schema: dict[str, Any]


class MCPStdioClient:
    """JSON-RPC over a subprocess's stdin/stdout.

    Lifecycle::

        client = MCPStdioClient(["uvx", "mcp-server-fetch"])
        await client.start()
        tools = await client.list_tools()
        result = await client.call_tool("fetch", {"url": "..."})
        await client.aclose()

    The reader task demultiplexes responses by JSON-RPC ``id``; concurrent
    calls are safe and complete in arrival order. Notifications (frames
    without an ``id``) are logged at DEBUG and dropped.
    """

    def __init__(
        self,
        command: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        call_timeout_s: float = _DEFAULT_CALL_TIMEOUT_S,
    ) -> None:
        if not command:
            raise ValueError("MCPStdioClient requires a non-empty command list")
        self._command = list(command)
        self._env = env
        self._cwd = cwd
        self._call_timeout_s = call_timeout_s

        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._next_id = 1
        self._closing = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Spawn the subprocess and complete the ``initialize`` handshake.

        ``MCPError`` is raised if the binary isn't on ``PATH``, the
        subprocess exits before the handshake completes, or the server
        returns an incompatible protocol version.
        """
        if self._proc is not None:
            raise RuntimeError("MCPStdioClient.start() called twice")
        # Resolve the binary up-front so a typo in command[0] surfaces
        # immediately rather than as a cryptic subprocess error.
        if shutil.which(self._command[0]) is None and not os.path.isabs(self._command[0]):
            raise MCPError(f"mcp server binary not found on PATH: {self._command[0]!r}")
        env = {**os.environ, **(self._env or {})}
        self._proc = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=self._cwd,
        )
        self._reader_task = asyncio.create_task(self._reader())

        # Initialize handshake. The server SHOULD respond within a
        # second or two; if it doesn't, something is wrong with the
        # binary and we bail rather than hanging the orchestrator.
        try:
            await asyncio.wait_for(
                self._request(
                    "initialize",
                    {
                        "protocolVersion": _CLIENT_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": _CLIENT_INFO,
                    },
                ),
                timeout=_INIT_TIMEOUT_S,
            )
        except asyncio.TimeoutError as exc:
            await self.aclose()
            raise MCPError("mcp initialize handshake timed out") from exc

        # Spec requires the client to send ``notifications/initialized``
        # right after a successful initialize. No response expected.
        await self._send_notification("notifications/initialized", {})

    async def aclose(self) -> None:
        """Terminate the subprocess and stop the reader task.

        Idempotent; safe to call even if ``start`` failed mid-way."""
        self._closing = True
        if self._proc is not None:
            with contextlib.suppress(ProcessLookupError):
                self._proc.terminate()
            with contextlib.suppress(asyncio.TimeoutError, ProcessLookupError):
                await asyncio.wait_for(self._proc.wait(), timeout=3.0)
            if self._proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    self._proc.kill()
            self._proc = None
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader_task
            self._reader_task = None
        # Fail any in-flight callers so they don't hang.
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(MCPError("mcp client closed"))
        self._pending.clear()

    # ------------------------------------------------------------------
    # RPC surface
    # ------------------------------------------------------------------
    async def list_tools(self) -> list[MCPToolInfo]:
        """Call ``tools/list`` and normalise into :class:`MCPToolInfo`."""
        result = await self._request("tools/list", {})
        tools_raw = result.get("tools")
        if not isinstance(tools_raw, list):
            raise MCPError(f"mcp tools/list: unexpected result shape: {result!r}")
        out: list[MCPToolInfo] = []
        for t in tools_raw:
            if not isinstance(t, dict):
                continue
            name = t.get("name")
            if not isinstance(name, str) or not name:
                continue
            description = t.get("description") or ""
            schema = t.get("inputSchema") or {"type": "object"}
            out.append(
                MCPToolInfo(
                    name=name,
                    description=str(description),
                    input_schema=schema if isinstance(schema, dict) else {"type": "object"},
                )
            )
        return out

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> str:
        """Call ``tools/call`` and return the concatenated text content.

        MCP allows the result to contain multiple content blocks of
        different ``type`` (text / image / resource). For the first pass
        we concatenate every ``text`` block and ignore the rest — the
        agent's prompt is text-only anyway.
        """
        result = await asyncio.wait_for(
            self._request("tools/call", {"name": name, "arguments": arguments}),
            timeout=self._call_timeout_s,
        )
        content = result.get("content")
        if not isinstance(content, list):
            raise MCPError(f"mcp tools/call({name}): unexpected result: {result!r}")
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        # Some servers signal failure with ``isError: true`` inside the
        # result envelope rather than a JSON-RPC error. Bubble that up.
        if result.get("isError"):
            raise MCPError("\n".join(parts) or f"mcp tool {name!r} reported an error")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Transport internals
    # ------------------------------------------------------------------
    async def _send_line(self, payload: dict[str, Any]) -> None:
        assert self._proc is not None
        assert self._proc.stdin is not None
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        self._proc.stdin.write(line.encode("utf-8"))
        await self._proc.stdin.drain()

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Fire-and-forget JSON-RPC notification (no ``id``, no response)."""
        await self._send_line({"jsonrpc": "2.0", "method": method, "params": params})

    async def _request(self, method: str, params: dict[str, Any]) -> Any:
        """Send a request and await the matching response."""
        if self._proc is None:
            raise MCPError("mcp client not started")
        req_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[req_id] = fut
        try:
            await self._send_line(
                {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            )
            return await fut
        finally:
            self._pending.pop(req_id, None)

    async def _reader(self) -> None:
        """Pump stdout → resolve pending futures by ``id``.

        Notifications (no ``id``) are logged at DEBUG. Stderr is drained
        in parallel by Python's subprocess module; we read it lazily
        only when something looks wrong.
        """
        assert self._proc is not None
        assert self._proc.stdout is not None
        while not self._closing:
            line_bytes = await self._proc.stdout.readline()
            if not line_bytes:
                # EOF — the server has exited. Surface this to anyone waiting.
                exc = MCPError("mcp server closed its stdout (exited?)")
                for fut in list(self._pending.values()):
                    if not fut.done():
                        fut.set_exception(exc)
                return
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                frame = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("mcp dropping non-JSON line: %r", line[:200])
                continue
            if not isinstance(frame, dict):
                logger.warning("mcp dropping non-object frame: %r", frame)
                continue
            if "id" not in frame:
                # Notification — useful for logging, but no caller to wake.
                logger.debug("mcp notification: %r", frame)
                continue
            fid = frame["id"]
            reply_fut: asyncio.Future[Any] | None = self._pending.get(fid)
            if reply_fut is None or reply_fut.done():
                continue
            if "error" in frame:
                err = frame["error"]
                msg = (
                    f"mcp error {err.get('code', '?')}: {err.get('message', err)!r}"
                    if isinstance(err, dict)
                    else f"mcp error: {err!r}"
                )
                reply_fut.set_exception(MCPError(msg))
            else:
                reply_fut.set_result(frame.get("result"))
