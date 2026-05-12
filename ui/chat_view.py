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

from collections.abc import AsyncIterator, Sequence
from typing import Any

from rich.cells import cell_len
from rich.console import Console
from rich.markup import escape as _md_escape
from rich.panel import Panel
from rich.table import Table

from core.streaming.events import Event
from ui.console import print_banner, print_divider
from ui.theme import DEFAULT, Theme

__all__ = ["ChatView", "Event"]

CommandGroup = tuple[str, Sequence[tuple[str, str]]]
"""A ``(section, [(cmd, desc), ...])`` pair rendered by :meth:`help_panel`.

``section`` is a group heading like ``"session"`` or ``"model"``.
"""

KeyHint = tuple[str, str]
"""``(keys, description)`` pair shown in the keys panel."""


# ---------------------------------------------------------------------------
# ANSI helpers — used only by stream_assistant's erase-and-redraw step.
# Plain ASCII CSI; works on any modern terminal (macOS Terminal, iTerm2,
# VS Code terminal, tmux, etc.).
# ---------------------------------------------------------------------------
_ANSI_UP_TO_LINE_START = "\x1b[F"  # move cursor to column 0 of previous line
_ANSI_ERASE_TO_END = "\x1b[J"  # clear from cursor to end of screen


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
        """Render the user's last input as a framed green block.

        Goal: turn boundaries the eye can scan. Each turn = (user panel,
        blank line, assistant block, blank line). The leading blank line
        is what separates this turn from the previous one — without it
        consecutive turns visually merge into a wall of text.
        """
        self.console.print()  # breathing room above
        # Each non-empty line gets a ``> `` prompt marker so multi-line
        # input still reads as a single block.
        body = "\n".join(
            f"[{self.theme.role_user}]>[/] {_md_escape(line)}" if line else ""
            for line in text.splitlines() or [text]
        )
        self.console.print(
            Panel(
                body,
                border_style=self.theme.role_user,
                padding=(0, 1),
                expand=True,
            )
        )

    def system_notice(self, text: str) -> None:
        """Inline ``· sys · text`` line — out-of-band ops, kept compact."""
        self._line("sys", text, self.theme.role_system)

    def tool_call_block(self, name: str, arguments: dict[str, Any]) -> None:
        """Render a ``tool_call`` event as an indented ``→ name(args)`` line.

        Indented two spaces so it visually nests under the surrounding
        assistant block instead of looking like a separate turn.
        """
        import json

        try:
            args_json = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            args_json = repr(arguments)
        if len(args_json) > 200:
            args_json = args_json[:197] + "…"
        self.console.print(
            f"  [{self.theme.role_tool}]→[/] [bold]{_md_escape(name)}[/]"
            f"[{self.theme.role_system}]({_md_escape(args_json)})[/]"
        )

    def tool_result_block(self, name: str, content: str, *, is_error: bool = False) -> None:
        """Render a ``tool_result`` event as an indented ``← name → body``.

        Mirrors :meth:`tool_call_block`'s indent so call+result read as a
        pair. Body is soft-capped at 320 chars for terminal readability;
        the LLM still gets the full payload via memory.
        """
        body = content if not is_error else f"[error] {content}"
        if len(body) > 320:
            body = body[:317] + "…"
        body = body.replace("\n", " ⏎ ")
        color = self.theme.error if is_error else self.theme.role_tool
        self.console.print(
            f"  [{color}]←[/] [bold]{_md_escape(name)}[/] "
            f"[{self.theme.role_system}]→[/] {_md_escape(body)}"
        )

    def assistant_block(self, text: str) -> None:
        """Render a fully-formed assistant message (history replay).

        Same layout as live streaming after :meth:`stream_assistant`'s
        markdown finalisation: dim ``assistant`` header on its own line,
        then the Markdown-rendered body, then a blank line. Used when
        switching sessions so the conversation looks consistent.
        """
        from ui.markdown import render_markdown

        self.console.print()
        self.console.print(f"[{self.theme.role_assistant}]assistant[/]")
        self.console.print(render_markdown(text))

    def error(self, code: str, message: str) -> None:
        self.console.print(f"[{self.theme.error}]✗ {code}[/]: {message}")

    # ------------------------------------------------------------------
    # Help panel
    # ------------------------------------------------------------------
    def help_panel(
        self,
        groups: Sequence[CommandGroup],
        key_hints: Sequence[KeyHint] = (),
    ) -> None:
        """Render the slash-command reference as a framed panel.

        Replaces the previous ``sys ·`` log-style rendering — one print
        call, grouped sections, columns auto-aligned. Use
        :class:`rich.table.Table` (grid mode) so long descriptions wrap
        gracefully on narrow terminals instead of overflowing into the
        next column.
        """
        commands = Table.grid(padding=(0, 2), expand=False)
        commands.add_column(no_wrap=True)
        commands.add_column(overflow="fold")
        for idx, (section, items) in enumerate(groups):
            if idx > 0:
                commands.add_row("", "")  # blank spacer between groups
            commands.add_row(
                f"[{self.theme.role_assistant}]{_md_escape(section)}[/]",
                "",
            )
            # Signatures contain ``[id|idx]`` / ``[on|off]`` — Rich would
            # parse those as markup tags and drop them. Escape both the
            # command and the description before wrapping in style tags.
            for cmd, desc in items:
                commands.add_row(
                    f"  [bold]{_md_escape(cmd)}[/]",
                    f"[{self.theme.role_system}]{_md_escape(desc)}[/]",
                )
        self.console.print(
            Panel(
                commands,
                title="[bold]slash commands[/]",
                title_align="left",
                border_style=self.theme.divider,
                padding=(1, 2),
            )
        )
        if key_hints:
            keys = Table.grid(padding=(0, 2), expand=False)
            keys.add_column(no_wrap=True)
            keys.add_column(overflow="fold")
            for combo, desc in key_hints:
                keys.add_row(
                    f"[bold]{_md_escape(combo)}[/]",
                    f"[{self.theme.role_system}]{_md_escape(desc)}[/]",
                )
            self.console.print(
                Panel(
                    keys,
                    title="[bold]keys[/]",
                    title_align="left",
                    border_style=self.theme.divider,
                    padding=(0, 2),
                )
            )

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------
    async def stream_assistant(self, events: AsyncIterator[Event]) -> str:
        """Consume an Event iterator, render incrementally, return full text.

        Layout (matches :meth:`assistant_block` so live + replay look identical)::

            <blank>
            assistant                        ← dim cyan header
            <streamed tokens>                ← raw, no per-line prefix
            <optional tool_call / result>    ← indented ``→`` / ``←``
            <streamed tokens, continued>
            ↳ 1234 ms                        ← dim duration footer
        """

        # Vertical breathing space + a single header line. The header
        # never re-prints during the same stream (tool calls just nest
        # underneath); semantically this whole block is one assistant turn.
        self.console.print()
        self.console.print(f"[{self.theme.role_assistant}]assistant[/]")

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
                    # ``retrieval`` fires once at turn-start, before any
                    # tokens. If parts is empty here, the notice sits
                    # ABOVE the streamed tokens — finalisation can still
                    # ANSI-erase just the token rows. Only if tokens were
                    # already mid-flight do we need to abort finalisation.
                    interrupted_tokens = bool(parts)
                    if interrupted_tokens:
                        self.console.out("", end="\n")
                    hits = event.get("hits") or []
                    if hits:
                        # Compact ``[1] title  [2] title`` so the user can
                        # correlate ``[N]`` markers in the assistant's reply
                        # back to actual sources without scrolling.
                        titles = "  ".join(
                            f"[{i}] {(h.get('title') or '(untitled)')[:40]}"
                            for i, h in enumerate(hits, start=1)
                        )
                        self.system_notice(
                            f"retrieved {len(hits)} chunk(s) · {titles}"
                        )
                    else:
                        self.system_notice("retrieved 0 chunks")
                    if interrupted_tokens:
                        had_mid_stream_notice = True
                elif etype == "tool_call":
                    if parts:
                        self.console.out("", end="\n")
                    self.tool_call_block(
                        str(event.get("tool_name", "")),
                        event.get("arguments") or {},
                    )
                    # ReAct tool dispatch interrupts the token stream; the
                    # next iteration's tokens continue beneath the tool
                    # block. parts is reset so the post-tool answer can
                    # still get markdown-finalised in isolation — finalize
                    # math walks back over the LAST contiguous token run.
                    parts.clear()
                elif etype == "tool_result":
                    self.tool_result_block(
                        str(event.get("tool_name", "")),
                        str(event.get("content", "")),
                        is_error=bool(event.get("is_error")),
                    )
                    parts.clear()
                elif etype == "thought":
                    interrupted_tokens = bool(parts)
                    if interrupted_tokens:
                        self.console.out("", end="\n")
                    text = str(event.get("text", "")).strip()
                    if text:
                        self.system_notice(f"thinking: {text}")
                    if interrupted_tokens:
                        had_mid_stream_notice = True
                elif etype == "done":
                    finished = True
                    self.console.out("", end="\n")
                    full = "".join(parts)
                    if full and not had_mid_stream_notice:
                        self._finalize_as_markdown(full)
                    duration = event.get("duration_ms")
                    if duration is not None:
                        self.console.print(
                            f"[{self.theme.divider}]↳ {duration} ms[/]"
                        )
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

    def _finalize_as_markdown(self, full_text: str) -> None:
        """Re-render the streamed reply as Markdown.

        Two regimes:

        * **Short reply** (fits the viewport) — ANSI-backspace over the
          raw stream and reprint the same block as Markdown in place.
          The user sees an in-place upgrade: plain → highlighted.
        * **Long reply** (taller than the viewport) — top rows have
          already scrolled off; ``\\x1b[F`` past them would corrupt
          previous output. Append a divider and reprint Markdown below
          the plain stream.

        Skipped when a ``retrieval`` / ``thought`` system notice was
        printed mid stream — our cursor math can no longer reach back
        cleanly across it.
        """
        from ui.markdown import render_markdown

        width = self.console.size.width
        height = self.console.size.height

        # Now that there's no per-line prefix, row math is straightforward
        # ceil-div of each line's cell count by terminal width.
        total_rows = _visual_rows(full_text, width)
        md = render_markdown(full_text)

        if total_rows + 2 < height:
            self.console.file.write(_ANSI_UP_TO_LINE_START * total_rows)
            self.console.file.write(_ANSI_ERASE_TO_END)
            self.console.file.flush()
            self.console.print(md)
            return

        self.console.print(
            f"[{self.theme.divider}]─── rendered ───[/]",
        )
        self.console.print(md)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _line(self, role: str, text: str, color: str) -> None:
        """Render a single inline ``· role · text`` notice line.

        Used for ``sys`` notices — out-of-band signals (retrieval, errors,
        ``/help`` echoes) that don't belong to a turn. Subdued styling
        keeps them visually distinct from user / assistant blocks.
        """
        self.console.print(
            f"[{self.theme.divider}]·[/] [{color}]{role}[/] · {text}"
        )
