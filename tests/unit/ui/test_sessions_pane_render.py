"""Sidebar render output — text/style tuples carry the right markers."""

from __future__ import annotations

from typing import Any

from ui.sessions_pane import render_sessions_lines
from ui.state import SessionRow, TuiState


def _join_text(tuples: list[Any]) -> str:
    return "".join(t[1] for t in tuples)


def test_empty_sessions_shows_placeholder() -> None:
    state = TuiState()
    text = _join_text(list(render_sessions_lines(state, focused=True)))
    assert "(no sessions yet)" in text
    assert "Ctrl+N" in text


def test_cursor_and_current_markers() -> None:
    state = TuiState(
        sessions=[
            SessionRow(id="aaa", title="Rust 进阶", message_count=3),
            SessionRow(id="bbb", title="Python 异步", message_count=7),
        ],
        current_session_id="bbb",
        sidebar_cursor=0,
    )
    tuples = list(render_sessions_lines(state, focused=True))
    text = _join_text(tuples)
    # Current session is "bbb" so it gets the ▸ marker on its own line.
    assert "▸" in text
    assert "Rust 进阶" in text
    assert "Python 异步" in text
    # Cursor (index 0) row should have the "reverse" style applied.
    cursor_styles = [t[0] for t in tuples if "Rust 进阶" in t[1]]
    assert any("reverse" in s for s in cursor_styles)
