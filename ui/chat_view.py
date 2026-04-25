"""Chat view — opencode-style presentation layer.

Streaming strategy (AGENTS.md §11 + Rich issue #1054 workaround):

1. While tokens arrive, write plain text straight to stdout. No
   :class:`rich.live.Live`, no markup parsing — scrolling is the
   terminal's job, nothing ever gets cropped or re-pushed.
2. When the ``done`` event fires, if the streamed block still fits
   inside the current viewport, erase it in place and reprint it as
   rendered Markdown (code highlighting, headings, lists). If it's
   taller than the viewport, leave the plain text alone — the top of
   the reply is already in scrollback and trying to ANSI-back-up over
   it would corrupt the screen.

Net effect: short replies look nice (Markdown), long replies stay
readable (plain), and there is never an infinite-scroll redraw loop.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal, TypedDict

from rich.cells import cell_len
from rich.console import Console

from ui.console import print_banner, print_divider
from ui.theme import DEFAULT, Theme

__all__ = ["ChatView", "Event"]


# ---------------------------------------------------------------------------
# ANSI helpers — used only by stream_assistant's erase-and-redraw step.
# Plain ASCII CSI; works on any modern terminal (macOS Terminal, iTerm2,
# VS Code terminal, tmux, etc.).
# ---------------------------------------------------------------------------
_ANSI_UP_TO_LINE_START = "\x1b[F"  # move cursor to column 0 of previous line
_ANSI_ERASE_TO_END = "\x1b[J"  # clear from cursor to end of screen


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


def _visual_rows(text: str, width: int) -> int:
    """Count how many terminal rows ``text`` occupies at the given width.

    Handles wide (CJK/emoji) chars via :func:`rich.cells.cell_len` and
    treats every explicit ``\\n`` as a hard break. Empty lines still take
    one row.
    """
    if width <= 0:
        return 1
    rows = 0
    for line in text.split("\n"):
        cells = cell_len(line)
        # An empty line still occupies 1 row; else ceil-div by width.
        rows += max(1, -(-cells // width))
    return rows


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

    def assistant_block(self, text: str) -> None:
        """Render a fully-formed assistant message (no streaming).

        Used to replay history when switching sessions. Markdown formatting
        is applied here because the complete text is known up-front, so
        layout is stable.
        """
        from ui.markdown import render_markdown

        prefix = f"[{self.theme.divider}]│ [/][{self.theme.role_assistant}]asst[/] · "
        self.console.print(prefix, end="")
        self.console.print(render_markdown(text))

    def error(self, code: str, message: str) -> None:
        self.console.print(f"[{self.theme.error}]✗ {code}[/]: {message}")

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------
    async def stream_assistant(self, events: AsyncIterator[Event]) -> str:
        """Consume an Event iterator, render incrementally, return full text."""

        prefix_markup = f"[{self.theme.divider}]│ [/][{self.theme.role_assistant}]asst[/] · "
        # Number of visible cells the prefix occupies on screen: "│ asst · "
        prefix_cells = cell_len("│ asst · ")
        self.console.print(prefix_markup, end="")

        parts: list[str] = []
        finished = False
        had_mid_stream_notice = False
        try:
            async for event in events:
                etype = event.get("type")
                if etype == "token":
                    delta = event.get("delta", "")
                    if delta:
                        parts.append(delta)
                        # Console.out bypasses markup so raw ``[foo]`` in
                        # LLM output isn't mistaken for a rich tag.
                        self.console.out(delta, end="", highlight=False)
                elif etype == "retrieval":
                    if parts:
                        self.console.out("", end="\n")
                    hits = event.get("hits") or []
                    self.system_notice(f"retrieved {len(hits)} chunk(s)")
                    if parts:
                        # We printed an intermediate sys line inside the
                        # asst block; we can no longer safely ANSI-erase
                        # back to the top, so the markdown re-render is
                        # skipped for this turn.
                        had_mid_stream_notice = True
                        self.console.print(prefix_markup, end="")
                elif etype == "done":
                    finished = True
                    self.console.out("", end="\n")
                    full = "".join(parts)
                    if full and not had_mid_stream_notice:
                        self._finalize_as_markdown(full, prefix_cells, prefix_markup)
                    duration = event.get("duration_ms")
                    if duration is not None:
                        self.system_notice(f"done in {duration} ms")
                    break
                elif etype == "error":
                    self.console.out("", end="\n")
                    self.error(
                        event.get("code", "error"),
                        event.get("message", ""),
                    )
                    finished = True
                    break
                # ping/pong/user_message ignored at the view layer.
        finally:
            if not finished:
                # Terminate the line on Ctrl-C / network drop so the next
                # prompt doesn't land mid-line.
                self.console.out("", end="\n")
        return "".join(parts)

    def _finalize_as_markdown(
        self,
        full_text: str,
        prefix_cells: int,
        prefix_markup: str,
    ) -> None:
        """Render the streamed reply as Markdown after the token stream ends.

        Two regimes:

        * **Short reply** (fits the viewport) — ANSI-backspace over the raw
          stream and reprint the same block as Markdown, same position. The
          user effectively sees an in-place upgrade: plain → highlighted.
        * **Long reply** (taller than the viewport) — the top rows have
          already scrolled off; trying to walk back over them with
          ``\\x1b[F`` would corrupt previous output. Instead, append a
          divider and reprint the Markdown version below the plain text.
          Scrollback keeps the raw stream, the viewport shows the pretty
          version.

        Skipped entirely if a ``retrieval`` system notice was printed mid
        stream (our cursor math can no longer reach back to the asst line).
        """
        from ui.markdown import render_markdown

        width = self.console.size.width
        height = self.console.size.height

        first_line, _, rest = full_text.partition("\n")
        first_rows = max(1, -(-(cell_len(first_line) + prefix_cells) // max(1, width)))
        rest_rows = _visual_rows(rest, width) if rest else 0
        total_rows = first_rows + rest_rows

        md = render_markdown(full_text)

        # Short path: erase + reprint in place.
        if total_rows + 2 < height:
            self.console.file.write(_ANSI_UP_TO_LINE_START * total_rows)
            self.console.file.write(_ANSI_ERASE_TO_END)
            self.console.file.flush()
            self.console.print(prefix_markup, end="")
            self.console.print(md)
            return

        # Long path: append a divider + markdown below the raw stream.
        self.console.print(
            f"[{self.theme.divider}]│ ─ rendered ─[/]",
        )
        self.console.print(prefix_markup, end="")
        self.console.print(md)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _line(self, role: str, text: str, color: str) -> None:
        """Render a single ``│ role · text`` line."""

        self.console.print(f"[{self.theme.divider}]│ [/][{color}]{role}[/] · {text}")
