"""Transcript buffer — append-only line store backing the main pane.

The TUI's main pane consumes this buffer via :class:`TranscriptPaneControl`
(see ``ui/transcript_pane.py``). The buffer itself is GUI-agnostic: it
exposes plain Python methods you can call from anywhere (the streaming
loop, command handlers, error paths).

Lines are stored as ``(role, text, rendered)`` tuples. ``rendered=True``
means ``text`` is an ANSI-escaped Markdown render produced by
:func:`render_markdown_ansi` and the pane should pass it through
``prompt_toolkit.formatted_text.ANSI`` instead of escaping it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Literal

__all__ = ["Line", "Role", "TranscriptBuffer", "render_markdown_ansi"]


Role = Literal["user", "assistant", "system", "error"]


@dataclass(frozen=True, slots=True)
class Line:
    role: Role
    text: str
    rendered: bool = field(default=False)


def render_markdown_ansi(text: str) -> str:
    """Render Markdown text to an ANSI-escaped string via rich.

    Used by :meth:`TranscriptBuffer.end_assistant` to upgrade the streamed
    plain text into a pretty final form. This is the "accept the latency"
    trade-off discussed in v1.3.1: streaming stays plain text, the final
    line gets the full Markdown treatment once.

    Critical: we use :meth:`rich.console.Console.capture` so rich does
    **not** write to the real stdout. Direct ``console.print(...)``
    bypasses prompt_toolkit's terminal ownership in full-screen mode and
    causes the ANSI bytes to be reflected back as user input (Bug fixed
    in v1.3.2). On any rendering failure we fall back to ``text`` verbatim.
    """
    try:
        from rich.console import Console
        from rich.markdown import Markdown

        # Fixed 100-col width gives consistent wraps; the transcript pane
        # re-wraps further if the actual viewport is narrower.
        console = Console(
            width=100,
            color_system="truecolor",
            force_terminal=True,
            no_color=False,
            file=None,  # capture() will pin a StringIO
        )
        with console.capture() as capture:
            console.print(Markdown(text))
        return capture.get().rstrip("\n")
    except Exception:
        return text


class TranscriptBuffer:
    """Bounded queue of rendered lines.

    Capped at ``max_lines`` to keep memory bounded during long sessions.
    The cap is on lines, not bytes — typical assistant replies are 5-20
    lines so 1000 lines ≈ 50-200 turns, which is plenty for one CLI session.
    """

    def __init__(self, max_lines: int = 1000) -> None:
        self._lines: deque[Line] = deque(maxlen=max_lines)
        self._streaming_buffer: list[str] = []
        self._streaming = False

    # ------------------------------------------------------------------
    # Read API (consumed by TranscriptPaneControl)
    # ------------------------------------------------------------------
    def lines(self) -> list[Line]:
        """Snapshot of all lines plus the in-flight assistant chunk."""
        out = list(self._lines)
        if self._streaming:
            out.append(Line(role="assistant", text="".join(self._streaming_buffer)))
        return out

    def __len__(self) -> int:
        return len(self._lines) + (1 if self._streaming else 0)

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------
    def add_user(self, text: str) -> None:
        self._flush_streaming()
        self._lines.append(Line(role="user", text=text))

    def add_system(self, text: str) -> None:
        self._flush_streaming()
        self._lines.append(Line(role="system", text=text))

    def add_error(self, code: str, message: str) -> None:
        self._flush_streaming()
        self._lines.append(Line(role="error", text=f"{code}: {message}"))

    def start_assistant(self) -> None:
        """Open a streaming assistant line. Subsequent ``append_to_assistant``
        calls accumulate into the same line until :meth:`end_assistant`."""
        self._flush_streaming()
        self._streaming = True
        self._streaming_buffer = []

    def append_to_assistant(self, delta: str) -> None:
        if not self._streaming:
            # Defensive: someone forgot start_assistant. Behave like a single shot.
            self.start_assistant()
        self._streaming_buffer.append(delta)

    def end_assistant(self, *, duration_ms: int | None = None) -> None:
        """Commit the streaming buffer as one final assistant line.

        Upgrades the plain stream text to a rich-rendered Markdown ANSI
        block so the final view shows headings, code blocks, links etc.
        properly. The streamed plain text was already shown live; this
        replaces it with the prettier final form.
        """
        if not self._streaming:
            return
        text = "".join(self._streaming_buffer)
        self._streaming = False
        self._streaming_buffer = []
        if text:
            ansi = render_markdown_ansi(text)
            self._lines.append(Line(role="assistant", text=ansi, rendered=True))
        if duration_ms is not None:
            self._lines.append(Line(role="system", text=f"done in {duration_ms} ms"))

    def clear(self) -> None:
        self._lines.clear()
        self._streaming = False
        self._streaming_buffer = []

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _flush_streaming(self) -> None:
        """Force-close any in-flight assistant line.

        Called by every non-assistant write so a half-finished stream gets
        committed as its own line before the new line is appended. We
        deliberately do **not** rich-render here — half-streams are
        transient.
        """
        if self._streaming:
            text = "".join(self._streaming_buffer)
            self._streaming = False
            self._streaming_buffer = []
            if text:
                self._lines.append(Line(role="assistant", text=text))
