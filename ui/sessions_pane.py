"""Sidebar pane — list of sessions with cursor highlight.

Pure render: reads :class:`TuiState`, never mutates it. Cursor moves come
from keybindings in ``ui/app.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from prompt_toolkit.layout.controls import FormattedTextControl

from ui.state import TuiState

if TYPE_CHECKING:
    from prompt_toolkit.formatted_text import StyleAndTextTuples

__all__ = ["SessionsPaneControl", "render_sessions_lines"]


def _truncate(text: str, max_chars: int) -> str:
    """Unicode-aware truncation that adds an ellipsis if cut."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def render_sessions_lines(
    state: TuiState,
    *,
    width: int = 24,
    focused: bool = False,
) -> StyleAndTextTuples:
    """Build the prompt_toolkit style/text tuple list for the sidebar.

    Format per row::

        ▸ <title 18 chars>      <count 3 chars>

    The cursor row gets ``reverse`` style; the row matching
    ``state.current_session_id`` is prefixed with ``▸`` and bold.
    Padded to ``width`` so the divider column lines up.
    """
    out: list[tuple[str, str]] = []
    header_color = "fg:ansicyan bold" if focused else "fg:ansicyan"
    out.append((header_color, f"{'sessions'.ljust(width)}\n"))

    if not state.sessions:
        out.append(("fg:ansibrightblack", f"{'(no sessions yet)'.ljust(width)}\n"))
        out.append(("", "\n" * 3))
        out.append(("fg:ansibrightblack", "Ctrl+N  new\n"))
        return cast("StyleAndTextTuples", out)

    title_w = width - 2 - 4  # 2 for "▸ ", 4 for right-aligned count
    for i, row in enumerate(state.sessions):
        is_cursor = i == state.sidebar_cursor and focused
        is_current = row.id == state.current_session_id
        marker = "▸" if is_current else " "
        title = _truncate(row.title, title_w)
        count_str = f"{row.message_count:>3}"
        line = f"{marker} {title.ljust(title_w)}{count_str}\n"
        if is_cursor:
            style = "reverse bold"
        elif is_current:
            style = "fg:ansibrightcyan bold"
        else:
            style = ""
        out.append((style, line))

    # Help footer
    out.append(("", "\n"))
    out.append(("fg:ansibrightblack", "Ctrl+N  new\n"))
    out.append(("fg:ansibrightblack", "Ctrl+D  delete\n"))
    out.append(("fg:ansibrightblack", "Tab     focus\n"))
    return cast("StyleAndTextTuples", out)


class SessionsPaneControl(FormattedTextControl):
    """Read-only formatted control wrapping :func:`render_sessions_lines`."""

    def __init__(self, state: TuiState, *, get_focused: object | None = None) -> None:
        self._state = state
        self._get_focused = get_focused
        super().__init__(text=self._render, focusable=True, show_cursor=False)

    def _render(self) -> StyleAndTextTuples:
        focused = bool(self._get_focused()) if callable(self._get_focused) else False
        return render_sessions_lines(self._state, focused=focused)
