"""Chat view — opencode-style presentation layer.

Implements AGENTS.md §11 conventions:
- zero emojis; ``│ `` prefix with role-tagged colors
- ``rich.live.Live`` based incremental Markdown while streaming
- event schema aligned with AGENTS.md §5.3 (SSE/WS parity)

The view is intentionally decoupled from any business layer: it accepts an
``AsyncIterator[Event]`` and renders; it knows nothing about Ollama, HTTP,
DB, or auth.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal, TypedDict

from rich.console import Console
from rich.live import Live

from ui.console import print_banner, print_divider
from ui.markdown import IncrementalMarkdownBuffer
from ui.theme import DEFAULT, Theme

__all__ = ["ChatView", "Event"]


class Event(TypedDict, total=False):
    """Streaming event shape (AGENTS.md §5.3).

    Total=False means every field is optional; presence depends on ``type``.
    """

    type: Literal[
        "user_message",
        "retrieval",
        "token",
        "done",
        "error",
        "ping",
        "pong",
    ]
    delta: str
    hits: list[dict[str, Any]]
    message_id: str
    usage: dict[str, Any]
    duration_ms: int
    code: str
    message: str


class ChatView:
    """Render chat I/O with the opencode visual language."""

    def __init__(self, console: Console, theme: Theme = DEFAULT) -> None:
        self.console = console
        self.theme = theme

    # ------------------------------------------------------------------
    # Static lines
    # ------------------------------------------------------------------
    def banner(self, model: str) -> None:
        print_banner(self.console, model, self.theme)
        print_divider(self.console, self.theme)

    def user_echo(self, text: str) -> None:
        self._line("you", text, self.theme.role_user)

    def system_notice(self, text: str) -> None:
        self._line("sys", text, self.theme.role_system)

    def error(self, code: str, message: str) -> None:
        self.console.print(f"[{self.theme.error}]✗ {code}[/]: {message}")

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------
    async def stream_assistant(self, events: AsyncIterator[Event]) -> str:
        """Consume an Event iterator, render incrementally, return full text.

        - ``retrieval`` → one-line system notice listing hit count.
        - ``token``     → append delta and refresh the Markdown snapshot.
        - ``done``      → finalize, print duration if present.
        - ``error``     → print via :meth:`error` and stop.
        """

        buf = IncrementalMarkdownBuffer()
        prefix = f"[{self.theme.divider}]│ [/][{self.theme.role_assistant}]asst[/] · "
        # Seed with empty Markdown so Live has something to draw.
        with Live(
            buf.append(""),
            console=self.console,
            refresh_per_second=24,
            transient=False,
        ) as live:
            # Prefix is rendered once above the live region.
            self.console.print(prefix, end="")
            async for event in events:
                etype = event.get("type")
                if etype == "token":
                    live.update(buf.append(event.get("delta", "")))
                elif etype == "retrieval":
                    hits = event.get("hits") or []
                    self.system_notice(f"retrieved {len(hits)} chunk(s)")
                elif etype == "done":
                    duration = event.get("duration_ms")
                    if duration is not None:
                        self.system_notice(f"done in {duration} ms")
                    break
                elif etype == "error":
                    self.error(
                        event.get("code", "error"),
                        event.get("message", ""),
                    )
                    break
                # ping/pong/user_message are ignored on the view layer.
        return buf.text

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _line(self, role: str, text: str, color: str) -> None:
        """Render a single ``│ role · text`` line.

        Centralised so future style tweaks only touch one place.
        """

        self.console.print(f"[{self.theme.divider}]│ [/][{color}]{role}[/] · {text}")
