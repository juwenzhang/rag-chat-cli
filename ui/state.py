"""Mutable TUI state container — what the three panes render from.

Separated from ``ui/app.py`` so command handlers (``ui/commands.py``) and
the panes themselves can read/write the same struct without circular
imports.

Important: per AGENTS.md §3 the UI layer cannot import ``core/`` or
``db/``. ``SessionMeta`` looks like a domain object but it's deliberately
re-declared here as a *plain* dataclass — the orchestrator (``app/``)
converts ``core.memory.chat_memory.SessionMeta`` instances into this
local shape before handing them to the TUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

__all__ = ["SessionRow", "TuiState"]


@dataclass(frozen=True, slots=True)
class SessionRow:
    """One row in the sidebar. Mirrors ``core.memory.chat_memory.SessionMeta``."""

    id: str
    title: str
    message_count: int


FocusedPane = Literal["sidebar", "input"]
MemoryMode = Literal["file", "db", "file (db-unavailable)"]


@dataclass
class TuiState:
    """Single source of truth for what the three panes display.

    Mutated by command handlers and by the streaming loop in ``app/``.
    Panes are pure read-only consumers; they call back into
    :class:`prompt_toolkit.Application.invalidate` after a write.
    """

    # ------------------------------------------------------------
    # Data
    # ------------------------------------------------------------
    sessions: list[SessionRow] = field(default_factory=list)
    current_session_id: str | None = None

    # ------------------------------------------------------------
    # UI flags
    # ------------------------------------------------------------
    focused_pane: FocusedPane = "input"
    sidebar_visible: bool = True
    sidebar_cursor: int = 0  # index into sessions

    # ------------------------------------------------------------
    # Runtime config (mutable from /model, /rag, /think)
    # ------------------------------------------------------------
    current_model: str = "qwen2.5:1.5b"
    available_models: list[str] = field(default_factory=list)
    rag_enabled: bool = False
    think_enabled: bool = False

    # ------------------------------------------------------------
    # Auth shadow
    # ------------------------------------------------------------
    user_email: str | None = None
    memory_mode: MemoryMode = "file"

    # ------------------------------------------------------------
    # Transcript scroll — number of lines to lift the bottom anchor by.
    # 0 = pinned to most recent (default; auto-follows streaming).
    # >0 = scrolled up by N lines (PageUp/Up). Clamped at render time.
    # ------------------------------------------------------------
    transcript_scroll: int = 0
    #: Most-recent window height in rows, updated by TranscriptPaneControl
    #: on each render. Used to decide how many lines are "visible" so that
    #: PageUp/PageDown feel like page-sized jumps.
    transcript_viewport_height: int = 30

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------
    def current_session_title(self) -> str:
        if self.current_session_id is None:
            return "(no session)"
        for row in self.sessions:
            if row.id == self.current_session_id:
                return row.title
        return self.current_session_id[:8]

    def move_cursor(self, delta: int) -> None:
        if not self.sessions:
            self.sidebar_cursor = 0
            return
        n = len(self.sessions)
        self.sidebar_cursor = max(0, min(n - 1, self.sidebar_cursor + delta))

    def session_at_cursor(self) -> SessionRow | None:
        if not self.sessions:
            return None
        if 0 <= self.sidebar_cursor < len(self.sessions):
            return self.sessions[self.sidebar_cursor]
        return None
