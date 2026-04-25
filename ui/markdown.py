"""Safe Markdown rendering helpers.

Used by :meth:`ui.chat_view.ChatView.assistant_block` to render the final
(non-streamed) assistant message when replaying conversation history.

Streaming itself no longer uses Markdown — see the docstring on
:meth:`ui.chat_view.ChatView.stream_assistant` for why (Rich issue #1054).
"""

from __future__ import annotations

from rich.markdown import Markdown

__all__ = ["render_markdown"]

_CODE_THEME = "monokai"


def render_markdown(text: str) -> Markdown:
    """Build a Markdown renderable with fixed code-block theme.

    ``hyperlinks=False`` keeps behaviour predictable across terminals and
    avoids accidental OSC-8 escapes in piped output.
    """

    return Markdown(text, code_theme=_CODE_THEME, hyperlinks=False)
