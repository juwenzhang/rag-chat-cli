"""Transcript pane — main area, role-coloured lines.

Rendering strategy (v1.3.4): prompt_toolkit's ``Window.get_vertical_scroll``
proved unreliable for ``FormattedTextControl`` (the internal scroll
algorithm keeps clamping us back to 0). Instead, this control slices the
buffer itself: it only emits the ``state.transcript_viewport_height`` most
recent lines, offset by ``state.transcript_scroll``.

Effect:

* ``transcript_scroll = 0`` → shows the latest ``viewport_height`` lines
  (the "always follow bottom" behaviour streaming needs).
* ``transcript_scroll > 0`` → shifts the visible window up by N lines,
  so PageUp/PageDown actually *see* older content.

Since prompt_toolkit draws from the top, slicing at the buffer level
sidesteps its scroll arithmetic entirely.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from prompt_toolkit.formatted_text import ANSI, to_formatted_text
from prompt_toolkit.layout.controls import FormattedTextControl

from ui.state import TuiState
from ui.transcript import Line, TranscriptBuffer

if TYPE_CHECKING:
    from prompt_toolkit.formatted_text import StyleAndTextTuples

__all__ = ["TranscriptPaneControl", "render_transcript_lines"]


_ROLE_STYLE: dict[str, str] = {
    "user": "fg:ansigreen bold",
    "assistant": "fg:ansibrightcyan",
    "system": "fg:ansibrightblack",
    "error": "fg:ansired bold",
}

_ROLE_LABEL: dict[str, str] = {
    "user": "you ",
    "assistant": "asst",
    "system": "sys ",
    "error": "err ",
}


def render_transcript_lines(buf: TranscriptBuffer) -> StyleAndTextTuples:
    """Convert buffer lines into prompt_toolkit style/text tuples.

    Kept as a standalone function so unit tests can exercise the mapping
    without having to build a :class:`TuiState`.
    """
    out: list[tuple[str, str]] = []
    lines = buf.lines()
    if not lines:
        out.append(("fg:ansibrightblack", "(no messages yet — type below to start)\n"))
        return cast("StyleAndTextTuples", out)
    _emit_lines(out, lines)
    return cast("StyleAndTextTuples", out)


def _emit_lines(out: list[tuple[str, str]], lines: list[Line]) -> None:
    """Shared emit loop — writes role label + body for each line."""
    for line in lines:
        style = _ROLE_STYLE.get(line.role, "")
        label = _ROLE_LABEL.get(line.role, "    ")
        out.append(("fg:ansibrightblack", "│ "))
        out.append((style, f"{label} "))
        out.append(("fg:ansibrightblack", "· "))
        if line.rendered:
            ansi_tuples = to_formatted_text(ANSI(line.text))
            out.extend(cast("list[tuple[str, str]]", list(ansi_tuples)))
            out.append(("", "\n"))
        else:
            out.append(("", line.text + "\n"))


class TranscriptPaneControl(FormattedTextControl):
    """Slice-rendering transcript. See module docstring for rationale."""

    def __init__(self, buf: TranscriptBuffer, state: TuiState) -> None:
        self._buf = buf
        self._state = state
        super().__init__(text=self._render, focusable=False, show_cursor=False)

    def _render(self) -> StyleAndTextTuples:
        all_lines = self._buf.lines()
        if not all_lines:
            return cast(
                "StyleAndTextTuples",
                [("fg:ansibrightblack", "(no messages yet — type below to start)\n")],
            )

        n = len(all_lines)
        viewport = max(1, self._state.transcript_viewport_height)
        # Clamp scroll: can't scroll past the oldest line.
        max_scroll = max(0, n - viewport)
        scroll = max(0, min(self._state.transcript_scroll, max_scroll))
        # Write clamped value back so status bar shows a truthful number.
        self._state.transcript_scroll = scroll

        # Slice: show ``viewport`` lines ending at (n - scroll).
        end = n - scroll
        start = max(0, end - viewport)
        visible = all_lines[start:end]

        out: list[tuple[str, str]] = []
        # Hint banner when scrolled up so the user knows they're not at the bottom.
        if scroll > 0:
            out.append(
                (
                    "fg:ansiyellow reverse",
                    f" ↑ scrolled up {scroll} line(s) — press End to return to latest \n",
                )
            )
        _emit_lines(out, visible)
        return cast("StyleAndTextTuples", out)
