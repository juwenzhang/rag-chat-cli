"""Safe Markdown rendering helpers for streamed assistant output."""

from __future__ import annotations

from rich.markdown import Markdown

__all__ = ["IncrementalMarkdownBuffer", "render_markdown"]

_CODE_THEME = "monokai"


def render_markdown(text: str) -> Markdown:
    """Build a Markdown renderable with fixed code-block theme.

    ``hyperlinks=False`` keeps behaviour predictable across terminals and
    avoids accidental OSC-8 escapes in piped output.
    """

    return Markdown(text, code_theme=_CODE_THEME, hyperlinks=False)


class IncrementalMarkdownBuffer:
    """Accumulate streaming deltas and re-render as Markdown on demand.

    Tiny, stateful helper — used by :class:`ui.chat_view.ChatView` with
    ``rich.live.Live`` to redraw the assistant message as tokens arrive.
    """

    __slots__ = ("_buf",)

    def __init__(self) -> None:
        self._buf: list[str] = []

    def append(self, delta: str) -> Markdown:
        """Append a delta and return the current Markdown snapshot."""

        if delta:
            self._buf.append(delta)
        return render_markdown(self.text)

    @property
    def text(self) -> str:
        return "".join(self._buf)

    def reset(self) -> None:
        self._buf.clear()
