"""Single-line status bar at the very bottom of the TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from prompt_toolkit.layout.controls import FormattedTextControl

from ui.state import TuiState

if TYPE_CHECKING:
    from prompt_toolkit.formatted_text import StyleAndTextTuples

__all__ = ["StatusBarControl", "render_status_line"]


def _flag(label: str, on: bool) -> tuple[str, str]:
    style = "fg:ansigreen bold" if on else "fg:ansibrightblack"
    return (style, f"{label}:{'on' if on else 'off'}")


def render_status_line(state: TuiState) -> StyleAndTextTuples:
    parts: list[tuple[str, str]] = []
    sep = ("fg:ansibrightblack", " · ")

    parts.append(("fg:ansiyellow", f"model:{state.current_model}"))
    parts.append(sep)
    parts.append(_flag("rag", state.rag_enabled))
    parts.append(sep)
    parts.append(_flag("think", state.think_enabled))
    parts.append(sep)
    parts.append(("fg:ansicyan", f"mem:{state.memory_mode}"))
    if state.user_email:
        parts.append(sep)
        parts.append(("fg:ansigreen", f"user:{state.user_email}"))
    parts.append(sep)
    # Show live scroll offset so users (and me debugging) can confirm
    # PgUp/PgDn / wheel actually updates the state.
    parts.append(("fg:ansiyellow", f"scroll:{state.transcript_scroll}"))
    parts.append(sep)
    parts.append(
        (
            "fg:ansibrightblack",
            "Enter=send  Ctrl+P/N=scroll  Ctrl+U/F=page  Ctrl+R=rag  Ctrl+Q=quit",
        )
    )
    return cast("StyleAndTextTuples", parts)


class StatusBarControl(FormattedTextControl):
    def __init__(self, state: TuiState) -> None:
        self._state = state
        super().__init__(text=self._render, focusable=False, show_cursor=False)

    def _render(self) -> StyleAndTextTuples:
        return render_status_line(self._state)
