"""Input layer: prompt_toolkit wrapper + slash command dispatcher.

AGENTS.md §11:
- multi-line input, submit with ``Esc+Enter`` (``F2`` backup)
- ``↑/↓`` recall from file history
- bottom toolbar shows shortcuts
- pure presentation — no business / core imports here
"""

from __future__ import annotations

import difflib
import shlex
from collections.abc import Awaitable, Callable, Iterable, Sequence
from pathlib import Path

from prompt_toolkit import PromptSession as _PTSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings

__all__ = [
    "CommandSpec",
    "PromptSession",
    "SlashCompleter",
    "SlashDispatcher",
    "SlashHandler",
]

SlashHandler = Callable[[list[str]], Awaitable[None] | None]
CommandSpec = tuple[str, str]
"""``(name, description)`` pair — what the completer popup shows.

Name has no leading ``/``. Aliases that duplicate another command (e.g.
``exit`` for ``quit``) are typically omitted from the completer to keep
the menu uncluttered; they still work at dispatch time.
"""


def _default_history_path() -> Path:
    return Path.home() / ".config" / "rag-chat" / "history"


def _build_keybindings() -> KeyBindings:
    kb = KeyBindings()

    @kb.add("enter")
    def _submit_alt(event):  # type: ignore[no-untyped-def]
        event.current_buffer.validate_and_handle()

    @kb.add("f2")
    def _submit_f2(event):  # type: ignore[no-untyped-def]
        event.current_buffer.validate_and_handle()

    @kb.add("c-l")
    def _clear(event):  # type: ignore[no-untyped-def]
        event.app.renderer.clear()

    return kb


class SlashCompleter(Completer):
    """Pop a menu of slash commands while the user is typing.

    Triggers only when the *first token of the first line* starts with
    ``/``. Anything else (regular chat input, or arguments after the
    command name) yields no completions so the menu doesn't get in the
    way of normal typing.

    The provider is a callable returning the current command list, so
    callers can register commands lazily (after :class:`PromptSession`
    has been constructed) without rebuilding the completer.
    """

    def __init__(
        self,
        commands_provider: Callable[[], Iterable[CommandSpec]],
    ) -> None:
        self._provider = commands_provider

    def get_completions(  # type: ignore[no-untyped-def]
        self, document: Document, complete_event
    ):
        text = document.text_before_cursor
        # Only complete on the first line — multi-line user prose
        # shouldn't surface a command popup.
        first_line, _, _ = text.partition("\n")
        if "\n" in text:
            # cursor is past the first line
            return
        if not first_line.startswith("/"):
            return
        # Once the user types a space, they're past the command name;
        # leave completions to the (future) per-command arg completer.
        if " " in first_line:
            return
        prefix = first_line[1:]
        for name, desc in self._provider():
            if name.startswith(prefix):
                yield Completion(
                    text=name,
                    start_position=-len(prefix),
                    display=f"/{name}",
                    display_meta=desc,
                )


class PromptSession:
    """Thin wrapper around :class:`prompt_toolkit.PromptSession`."""

    def __init__(
        self,
        history_path: Path | None = None,
        *,
        commands_provider: Callable[[], Sequence[CommandSpec]] | None = None,
    ) -> None:
        path = history_path or _default_history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        completer: Completer | None = (
            SlashCompleter(commands_provider) if commands_provider is not None else None
        )
        self._session: _PTSession[str] = _PTSession(
            history=FileHistory(str(path)),
            multiline=True,
            key_bindings=_build_keybindings(),
            completer=completer,
            complete_while_typing=True,
            bottom_toolbar=lambda: (
                "Enter send · / commands · Tab complete · ↑↓ history · Ctrl+L clear"
            ),
        )

    async def prompt_async(self, prompt: str = "› ") -> str:
        return await self._session.prompt_async(prompt)


class SlashDispatcher:
    """Route ``/<name> <args...>`` lines to registered handlers.

    Unknown ``/<name>`` lines are *intentionally* swallowed (not forwarded
    upstream) so a typo like ``/ollama-ath`` never reaches the LLM with a
    secret in the args. Set ``on_unknown`` to render a friendly suggestion.
    """

    UnknownHandler = Callable[[str, list[str]], None]

    def __init__(self, on_unknown: UnknownHandler | None = None) -> None:
        self._handlers: dict[str, SlashHandler] = {}
        self._on_unknown = on_unknown

    def register(self, name: str, fn: SlashHandler) -> None:
        key = name.lstrip("/")
        self._handlers[key] = fn

    def set_on_unknown(self, fn: UnknownHandler) -> None:
        """Late binding — run_legacy_chat needs the dispatcher before it
        has a ``view`` to render the error to."""
        self._on_unknown = fn

    def registered(self) -> list[str]:
        return sorted(self._handlers.keys())

    def closest(self, name: str, n: int = 1) -> list[str]:
        """Return up to ``n`` registered command names closest to ``name``."""
        return difflib.get_close_matches(name, self.registered(), n=n, cutoff=0.5)

    async def dispatch(self, line: str) -> bool:
        """Return True iff the line started with ``/``.

        - Known command → run handler, return True.
        - Unknown command → invoke ``on_unknown`` (if set), return True.
          The line is *consumed* either way; callers must not fall back to
          treating it as user prose.
        - Plain text (no leading ``/``) → return False.
        """

        stripped = line.strip()
        if not stripped.startswith("/"):
            return False
        try:
            parts = shlex.split(stripped[1:])
        except ValueError:
            parts = stripped[1:].split()
        if not parts:
            # bare `/` — nothing to dispatch; treat as no-op handled.
            return True
        name, *args = parts
        handler = self._handlers.get(name)
        if handler is None:
            if self._on_unknown is not None:
                self._on_unknown(name, args)
            return True  # consumed — never forward to LLM
        result = handler(args)
        if result is not None:
            await result
        return True
