"""Slash command registry for the TUI.

Every command takes ``(ctx, args)`` and returns ``None``. The context object
holds dependencies (``state`` / ``transcript`` / ``services``) so commands
themselves stay free of FastAPI / SQLAlchemy / prompt_toolkit imports —
they just orchestrate.

Adding a new command:

1. Write ``async def _cmd_foo(ctx, args): ...``
2. Register it in :func:`register_default_commands` with a one-line help
3. The ``/help`` command will pick it up automatically.
"""

from __future__ import annotations

import shlex
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ui.state import TuiState
from ui.transcript import TranscriptBuffer

__all__ = [
    "CommandContext",
    "CommandHandler",
    "CommandRegistry",
    "register_default_commands",
]


CommandHandler = Callable[["CommandContext", list[str]], Awaitable[None]]


@dataclass
class CommandContext:
    """Read/write surface every command receives.

    ``services`` is intentionally typed loosely (``object``) so this module
    never imports anything from ``core/`` / ``app/`` directly. The
    orchestrator (``app/chat_app.py``) constructs the services bag and
    casts it back to the concrete type inside each handler that needs it.
    """

    state: TuiState
    transcript: TranscriptBuffer
    services: object  # actually app.chat_app.TuiServices, kept loose to break cycle


@dataclass
class _Entry:
    handler: CommandHandler
    summary: str


class CommandRegistry:
    """Map ``"name"`` → handler with one-line help summary."""

    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}

    def register(self, name: str, fn: CommandHandler, *, summary: str = "") -> None:
        self._entries[name.lstrip("/")] = _Entry(handler=fn, summary=summary)

    def names(self) -> list[str]:
        return sorted(self._entries.keys())

    def help_lines(self) -> list[tuple[str, str]]:
        return [(n, self._entries[n].summary) for n in self.names()]

    async def dispatch(self, ctx: CommandContext, line: str) -> bool:
        """Return ``True`` iff ``line`` was a recognised slash command."""
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
        entry = self._entries.get(name)
        if entry is None:
            ctx.transcript.add_error("unknown_command", f"/{name}")
            return True  # consumed (don't send to LLM)
        await entry.handler(ctx, args)
        return True


# ---------------------------------------------------------------------------
# Built-in handlers
# ---------------------------------------------------------------------------


async def _cmd_help(ctx: CommandContext, args: list[str]) -> None:
    del args
    ctx.transcript.add_system("commands:")
    # Pull the registry off the services bag — set up by register_default_commands.
    registry: CommandRegistry | None = getattr(ctx.services, "command_registry", None)
    if registry is None:
        return
    for name, summary in registry.help_lines():
        ctx.transcript.add_system(f"  /{name:<10} {summary}")


async def _cmd_quit(ctx: CommandContext, args: list[str]) -> None:
    del args
    # Actual exit happens via the keybinding Ctrl+Q. Here we just leave a
    # marker — the orchestrator polls ``transcript`` after each turn.
    ctx.transcript.add_system("type Ctrl+Q to quit (or close the terminal)")


async def _cmd_clear(ctx: CommandContext, args: list[str]) -> None:
    del args
    ctx.transcript.clear()


async def _cmd_rag(ctx: CommandContext, args: list[str]) -> None:
    if not args or args[0].lower() not in ("on", "off"):
        ctx.transcript.add_error("rag", "usage: /rag on|off")
        return
    ctx.state.rag_enabled = args[0].lower() == "on"
    ctx.transcript.add_system(f"rag → {'on' if ctx.state.rag_enabled else 'off'}")


async def _cmd_think(ctx: CommandContext, args: list[str]) -> None:
    if not args or args[0].lower() not in ("on", "off"):
        ctx.transcript.add_error("think", "usage: /think on|off")
        return
    ctx.state.think_enabled = args[0].lower() == "on"
    ctx.transcript.add_system(f"think → {'on' if ctx.state.think_enabled else 'off'}")


async def _cmd_model(ctx: CommandContext, args: list[str]) -> None:
    """``/model`` lists; ``/model <name>`` switches."""
    state = ctx.state
    if not args:
        if not state.available_models:
            ctx.transcript.add_system("no models discovered (is ollama running?)")
            return
        ctx.transcript.add_system("models:")
        for name in state.available_models:
            mark = " *" if name == state.current_model else ""
            ctx.transcript.add_system(f"  {name}{mark}")
        return
    target = args[0]
    if state.available_models and target not in state.available_models:
        ctx.transcript.add_error("model", f"unknown: {target}; /model to list")
        return
    state.current_model = target
    # Forward to the provider so the next reply uses the new model.
    set_provider_model = getattr(ctx.services, "set_provider_model", None)
    if callable(set_provider_model):
        set_provider_model(target)
    ctx.transcript.add_system(f"model → {target}")


# Auth / session commands delegate back to services callbacks so this module
# stays decoupled from core/db/app. The orchestrator wires these up.


async def _cmd_register(ctx: CommandContext, args: list[str]) -> None:
    del args
    fn: Callable[[], Awaitable[None]] | None = getattr(ctx.services, "do_register", None)
    if fn is None:
        ctx.transcript.add_error("register", "auth not available")
        return
    await fn()


async def _cmd_login(ctx: CommandContext, args: list[str]) -> None:
    del args
    fn: Callable[[], Awaitable[None]] | None = getattr(ctx.services, "do_login", None)
    if fn is None:
        ctx.transcript.add_error("login", "auth not available")
        return
    await fn()


async def _cmd_logout(ctx: CommandContext, args: list[str]) -> None:
    del args
    fn: Callable[[], Awaitable[None]] | None = getattr(ctx.services, "do_logout", None)
    if fn is None:
        ctx.transcript.add_error("logout", "auth not available")
        return
    await fn()


async def _cmd_whoami(ctx: CommandContext, args: list[str]) -> None:
    del args
    if ctx.state.user_email:
        ctx.transcript.add_system(f"user: {ctx.state.user_email} (memory: {ctx.state.memory_mode})")
    else:
        ctx.transcript.add_system(f"not logged in (memory: {ctx.state.memory_mode})")


async def _cmd_new(ctx: CommandContext, args: list[str]) -> None:
    fn: Callable[[str | None], Awaitable[None]] | None = getattr(
        ctx.services, "do_new_session", None
    )
    if fn is None:
        ctx.transcript.add_error("new", "session ops not available")
        return
    title = " ".join(args) if args else None
    await fn(title)


async def _cmd_switch(ctx: CommandContext, args: list[str]) -> None:
    if not args:
        ctx.transcript.add_error("switch", "usage: /switch <session_id_or_index>")
        return
    target = args[0]
    # Allow numeric index into the sidebar list as a shortcut.
    if target.isdigit():
        idx = int(target)
        if 0 <= idx < len(ctx.state.sessions):
            target = ctx.state.sessions[idx].id
        else:
            ctx.transcript.add_error("switch", f"index out of range: {idx}")
            return
    fn: Callable[[str], Awaitable[None]] | None = getattr(ctx.services, "do_switch_session", None)
    if fn is None:
        ctx.transcript.add_error("switch", "session ops not available")
        return
    await fn(target)


async def _cmd_title(ctx: CommandContext, args: list[str]) -> None:
    if not args:
        ctx.transcript.add_error("title", "usage: /title <new title>")
        return
    new_title = " ".join(args)
    fn: Callable[[str], Awaitable[None]] | None = getattr(
        ctx.services, "do_set_current_title", None
    )
    if fn is None:
        ctx.transcript.add_error("title", "session ops not available")
        return
    await fn(new_title)


async def _cmd_delete(ctx: CommandContext, args: list[str]) -> None:
    del args
    fn: Callable[[], Awaitable[None]] | None = getattr(ctx.services, "do_delete_current", None)
    if fn is None:
        ctx.transcript.add_error("delete", "session ops not available")
        return
    await fn()


async def _cmd_sessions(ctx: CommandContext, args: list[str]) -> None:
    del args
    fn: Callable[[], Awaitable[None]] | None = getattr(ctx.services, "do_refresh_sessions", None)
    if fn is None:
        ctx.transcript.add_error("sessions", "session ops not available")
        return
    await fn()
    ctx.transcript.add_system(f"{len(ctx.state.sessions)} session(s)")


def register_default_commands(registry: CommandRegistry) -> None:
    """Populate ``registry`` with the v1 command set."""
    registry.register("help", _cmd_help, summary="show this list")
    registry.register("quit", _cmd_quit, summary="quit (Ctrl+Q also works)")
    registry.register("exit", _cmd_quit, summary="alias for /quit")
    registry.register("clear", _cmd_clear, summary="clear transcript pane")

    registry.register("model", _cmd_model, summary="list models, or /model <name> to switch")
    registry.register("rag", _cmd_rag, summary="/rag on|off")
    registry.register("think", _cmd_think, summary="/think on|off")

    registry.register("register", _cmd_register, summary="create a new account")
    registry.register("login", _cmd_login, summary="sign in (memory switches to db)")
    registry.register("logout", _cmd_logout, summary="sign out (memory switches to file)")
    registry.register("whoami", _cmd_whoami, summary="show current user / memory mode")

    registry.register("sessions", _cmd_sessions, summary="refresh sidebar from storage")
    registry.register("new", _cmd_new, summary="new session, optional title")
    registry.register("switch", _cmd_switch, summary="/switch <id|index>")
    registry.register("title", _cmd_title, summary="/title <text> — rename current (db only)")
    registry.register("delete", _cmd_delete, summary="delete current session")
