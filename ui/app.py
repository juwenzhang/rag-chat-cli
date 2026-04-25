"""prompt_toolkit Application — wires the three panes + keybindings.

The TUI takes over the terminal in full-screen mode. ``app/chat_app.py``
constructs an Application via :func:`build_application` and runs it.

Keybindings (all vi-free, opencode/cursor-style):

================  =========================================================
Key               Action
================  =========================================================
Esc, Enter        Submit input (multi-line in box, Enter alone = newline)
Tab               Rotate focus sidebar ↔ input
Ctrl+B            Toggle sidebar visibility
Ctrl+N            New session
Ctrl+D            Delete current session (must be on sidebar to confirm)
Ctrl+L            Clear transcript
Ctrl+Q            Quit
↑ / ↓             Move sidebar cursor (when sidebar focused)
Enter             Switch to selected session (when sidebar focused)
================  =========================================================
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from prompt_toolkit import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    ConditionalContainer,
    HSplit,
    Layout,
    VSplit,
    Window,
)
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea

from ui.sessions_pane import SessionsPaneControl
from ui.state import TuiState
from ui.status_bar import StatusBarControl
from ui.transcript import TranscriptBuffer
from ui.transcript_pane import TranscriptPaneControl

if TYPE_CHECKING:
    from prompt_toolkit.key_binding.key_processor import KeyPressEvent

__all__ = ["build_application"]


SendCallback = Callable[[str], Awaitable[None]]
SwitchCallback = Callable[[str], Awaitable[None]]
SimpleCallback = Callable[[], Awaitable[None]]


_STYLE = Style.from_dict(
    {
        # Override default ``input.background`` so the input box stands out
        # subtly on dark terminals.
        "frame.border": "fg:ansibrightblack",
    }
)


def build_application(
    state: TuiState,
    transcript: TranscriptBuffer,
    *,
    on_send: SendCallback,
    on_switch: SwitchCallback,
    on_new_session: SimpleCallback,
    on_delete_current: SimpleCallback,
) -> Application[None]:
    """Assemble the Application. Caller runs ``await app.run_async()``.

    Callbacks are intentionally async — they may touch the network (DB / LLM).
    """

    sidebar_ctrl = SessionsPaneControl(state, get_focused=lambda: state.focused_pane == "sidebar")
    transcript_ctrl = TranscriptPaneControl(transcript, state)
    status_ctrl = StatusBarControl(state)

    input_box = TextArea(
        multiline=True,
        # Fixed height — without ``exact`` the HSplit will try to expand the
        # input box when the internal TextArea buffer scrolls (e.g. when a
        # stray PageUp moves its cursor), which visually compresses the
        # transcript pane above. Pin it and it cannot steal rows.
        height=Dimension.exact(4),
        prompt="› ",
        wrap_lines=True,
        scrollbar=False,
        focus_on_click=True,
    )

    sidebar_window = Window(
        sidebar_ctrl,
        width=Dimension.exact(28),
        wrap_lines=False,
        always_hide_cursor=True,
    )

    def _update_viewport_height() -> None:
        """Sync the current window height back into state.

        Called from the scroll keybindings so PageUp/PageDown can use a
        page size that matches what the user actually sees. Also called
        speculatively from the render callback so the slice used the next
        frame is correctly sized.
        """
        info = transcript_window.render_info
        if info is not None and info.window_height > 0:
            state.transcript_viewport_height = info.window_height

    transcript_window = Window(
        transcript_ctrl,
        wrap_lines=True,
        always_hide_cursor=True,
        right_margins=[ScrollbarMargin(display_arrows=True)],
    )

    body = VSplit(
        [
            ConditionalContainer(sidebar_window, filter=Condition(lambda: state.sidebar_visible)),
            ConditionalContainer(
                Window(width=1, char="│", style="fg:ansibrightblack"),
                filter=Condition(lambda: state.sidebar_visible),
            ),
            transcript_window,
        ]
    )

    root = HSplit(
        [
            body,
            Window(height=1, char="─", style="fg:ansibrightblack"),
            input_box,
            Window(status_ctrl, height=1, style="reverse"),
        ]
    )

    layout = Layout(root, focused_element=input_box)

    kb = _build_keybindings(
        state=state,
        input_box=input_box,
        on_send=on_send,
        on_switch=on_switch,
        on_new_session=on_new_session,
        on_delete_current=on_delete_current,
        transcript=transcript,
        transcript_window=transcript_window,
    )

    app: Application[None] = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=True,
        mouse_support=True,  # enables wheel scroll in transcript window
        style=_STYLE,
        # Force a redraw every 50 ms so streamed tokens visibly land in
        # transcript pane between explicit ``app.invalidate()`` calls.
        # Without this, prompt_toolkit batches invalidations and the user
        # sees a single "blob" appearing on done. 50 ms ≈ 20 fps which is
        # smooth enough and well below the per-token rate of qwen2.5:1.5b.
        refresh_interval=0.05,
    )

    # Stash references so callbacks can request a redraw via app.invalidate().
    setattr(app, "_tui_state", state)  # noqa: B010 — runtime attribute by design
    setattr(app, "_tui_transcript", transcript)  # noqa: B010
    setattr(app, "_tui_input_box", input_box)  # noqa: B010
    return app


def _build_keybindings(
    *,
    state: TuiState,
    input_box: TextArea,
    on_send: SendCallback,
    on_switch: SwitchCallback,
    on_new_session: SimpleCallback,
    on_delete_current: SimpleCallback,
    transcript: TranscriptBuffer,
    transcript_window: Window,
) -> KeyBindings:
    kb = KeyBindings()

    sidebar_focused = Condition(lambda: state.focused_pane == "sidebar")
    input_focused = Condition(lambda: state.focused_pane == "input")

    @kb.add("enter", filter=input_focused)
    def _submit_enter(event: KeyPressEvent) -> None:
        """Plain Enter sends the message (chat-app idiom).

        Multi-line input is still possible via ``Alt+Enter`` (handled
        below) — that inserts a newline instead of submitting.
        """
        text = input_box.text.strip()
        input_box.text = ""
        if not text:
            return

        async def _go() -> None:
            await on_send(text)
            event.app.invalidate()

        event.app.create_background_task(_go())

    @kb.add("escape", "enter", filter=input_focused)
    def _newline_alt(event: KeyPressEvent) -> None:
        """Alt/Esc + Enter inserts a literal newline for multi-line input."""
        event.current_buffer.insert_text("\n")

    @kb.add("c-q")
    def _quit(event: KeyPressEvent) -> None:
        event.app.exit()

    @kb.add("c-c")
    def _ctrl_c(event: KeyPressEvent) -> None:
        # v1 = quit. v2 will turn this into "abort current stream".
        event.app.exit()

    @kb.add("c-b")
    def _toggle_sidebar(event: KeyPressEvent) -> None:
        state.sidebar_visible = not state.sidebar_visible
        event.app.invalidate()

    @kb.add("c-r")
    def _toggle_rag(event: KeyPressEvent) -> None:
        state.rag_enabled = not state.rag_enabled
        transcript.add_system(f"rag → {'on' if state.rag_enabled else 'off'}")
        event.app.invalidate()

    @kb.add("c-t")
    def _toggle_think(event: KeyPressEvent) -> None:
        state.think_enabled = not state.think_enabled
        transcript.add_system(f"think → {'on' if state.think_enabled else 'off'}")
        event.app.invalidate()

    @kb.add("tab")
    def _rotate_focus(event: KeyPressEvent) -> None:
        if state.focused_pane == "input":
            state.focused_pane = "sidebar"
            # Don't actually move pt focus — sidebar isn't a real input.
            # The cursor only matters for visual highlighting.
        else:
            state.focused_pane = "input"
            event.app.layout.focus(input_box)
        event.app.invalidate()

    @kb.add("c-n")
    def _new(event: KeyPressEvent) -> None:
        async def _go() -> None:
            await on_new_session()
            event.app.invalidate()

        event.app.create_background_task(_go())

    @kb.add("c-d", filter=sidebar_focused)
    def _delete(event: KeyPressEvent) -> None:
        async def _go() -> None:
            await on_delete_current()
            event.app.invalidate()

        event.app.create_background_task(_go())

    @kb.add("c-l")
    def _clear(event: KeyPressEvent) -> None:
        transcript.clear()
        event.app.invalidate()

    # ---------------------------- Scroll keybindings -----------------------
    # v1.3.4: scroll is now implemented by slice-rendering in
    # ``TranscriptPaneControl`` — these keybindings just bump
    # ``state.transcript_scroll``; the control clamps + draws accordingly.

    # ---------------------------- Scroll keybindings -----------------------
    # v1.3.5: macOS Terminal.app intercepts PgUp / PgDn / Ctrl+↑ / Ctrl+↓
    # for its own scrollback navigation — they never reach the application.
    # So we provide Ctrl+P/N (line) + Ctrl+U/F (half-page) + Home/End that
    # all terminals pass through. PgUp/PgDn stay registered for iTerm2 /
    # Linux / tmux users where they work out of the box.

    def _page_size() -> int:
        info = transcript_window.render_info
        if info is not None and info.window_height > 0:
            state.transcript_viewport_height = info.window_height
        return max(1, state.transcript_viewport_height - 2)

    def _half_page() -> int:
        return max(1, _page_size() // 2)

    @kb.add("pageup", eager=True)
    @kb.add("c-u", eager=True)
    def _page_up(event: KeyPressEvent) -> None:
        state.transcript_scroll += _half_page()
        event.app.invalidate()

    @kb.add("pagedown", eager=True)
    @kb.add("c-f", eager=True)
    def _page_down(event: KeyPressEvent) -> None:
        state.transcript_scroll = max(0, state.transcript_scroll - _half_page())
        event.app.invalidate()

    @kb.add("c-p", eager=True)
    def _line_up(event: KeyPressEvent) -> None:
        """Line scroll up — Ctrl+P (vi ``previous``)."""
        state.transcript_scroll += 1
        event.app.invalidate()

    @kb.add("c-n", eager=True)
    def _line_down(event: KeyPressEvent) -> None:
        """Line scroll down — Ctrl+N (vi ``next``)."""
        state.transcript_scroll = max(0, state.transcript_scroll - 1)
        event.app.invalidate()

    @kb.add("home", eager=True)
    def _scroll_top(event: KeyPressEvent) -> None:
        state.transcript_scroll = 10**6
        event.app.invalidate()

    @kb.add("end", eager=True)
    def _scroll_bottom(event: KeyPressEvent) -> None:
        state.transcript_scroll = 0
        event.app.invalidate()

    @kb.add("up", filter=sidebar_focused)
    def _cursor_up(event: KeyPressEvent) -> None:
        state.move_cursor(-1)
        event.app.invalidate()

    @kb.add("down", filter=sidebar_focused)
    def _cursor_down(event: KeyPressEvent) -> None:
        state.move_cursor(+1)
        event.app.invalidate()

    @kb.add("enter", filter=sidebar_focused)
    def _switch(event: KeyPressEvent) -> None:
        row = state.session_at_cursor()
        if row is None:
            return

        async def _go() -> None:
            await on_switch(row.id)
            # Return focus to input after switching so the user can immediately
            # type a follow-up message.
            state.focused_pane = "input"
            event.app.layout.focus(input_box)
            event.app.invalidate()

        event.app.create_background_task(_go())

    return kb
