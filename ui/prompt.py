"""Input layer: prompt_toolkit wrapper + slash command dispatcher.

AGENTS.md §11:
- multi-line input, submit with ``Esc+Enter`` (``F2`` backup)
- ``↑/↓`` recall from file history
- bottom toolbar shows shortcuts
- pure presentation — no business / core imports here
"""

from __future__ import annotations

import shlex
from collections.abc import Awaitable, Callable
from pathlib import Path

from prompt_toolkit import PromptSession as _PTSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings

__all__ = ["PromptSession", "SlashDispatcher", "SlashHandler"]

SlashHandler = Callable[[list[str]], Awaitable[None] | None]


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


class PromptSession:
    """Thin wrapper around :class:`prompt_toolkit.PromptSession`."""

    def __init__(self, history_path: Path | None = None) -> None:
        path = history_path or _default_history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        self._session: _PTSession[str] = _PTSession(
            history=FileHistory(str(path)),
            multiline=True,
            key_bindings=_build_keybindings(),
            bottom_toolbar=lambda: "Enter send · ↑↓ history · /help",
        )

    async def prompt_async(self, prompt: str = "› ") -> str:
        return await self._session.prompt_async(prompt)


class SlashDispatcher:
    """Route ``/<name> <args...>`` lines to registered handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, SlashHandler] = {}

    def register(self, name: str, fn: SlashHandler) -> None:
        key = name.lstrip("/")
        self._handlers[key] = fn

    def registered(self) -> list[str]:
        return sorted(self._handlers.keys())

    async def dispatch(self, line: str) -> bool:
        """Return True iff the line was handled as a slash command."""

        stripped = line.strip()
        if not stripped.startswith("/"):
            return False
        try:
            parts = shlex.split(stripped[1:])
        except ValueError:
            parts = stripped[1:].split()
        if not parts:
            return False
        name, *args = parts
        handler = self._handlers.get(name)
        if handler is None:
            return False
        result = handler(args)
        if result is not None:
            await result
        return True
