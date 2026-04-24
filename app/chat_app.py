"""Orchestration layer — the one place that ties UI to the core layer.

AGENTS.md §3: ``app/`` is the only layer allowed to import both ``ui/`` and
``core/``.

The default :func:`run_chat` entry point builds a :class:`ChatServiceProvider`
that talks to a real Ollama server; if the server cannot be reached at start
time it transparently degrades to :class:`EchoReplyProvider` so the CLI still
boots in offline / test environments.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from ui import ChatView, PromptSession
from ui.chat_view import Event
from ui.console import make_console

__all__ = [
    "ChatServiceProvider",
    "EchoReplyProvider",
    "ReplyProvider",
    "build_default_chat_service",
    "build_default_provider",
    "run_chat",
]


class ReplyProvider(Protocol):
    """Contract between the orchestrator and the LLM service."""

    def reply(self, user_text: str, history: list[dict[str, Any]]) -> AsyncIterator[Event]: ...


class EchoReplyProvider:
    """Fallback provider — echoes the user text back as streamed tokens.

    Kept for two reasons:
      * offline / CI boots (no Ollama reachable);
      * smoke tests in ``tests/integration/test_cli_boot.py``.
    """

    async def reply(self, user_text: str, history: list[dict[str, Any]]) -> AsyncIterator[Event]:
        del history  # intentionally unused
        chunks = [f"echo: {user_text[:120]}"]
        for chunk in chunks:
            for word in chunk.split(" "):
                yield Event(type="token", delta=word + " ")
                await asyncio.sleep(0.01)
        yield Event(type="done", duration_ms=0)


class ChatServiceProvider:
    """Adapts :class:`core.chat_service.ChatService` to :class:`ReplyProvider`.

    One ``session_id`` is minted on first call; subsequent turns reuse it so
    :class:`ChatMemory` keeps accumulating history. Use
    :meth:`reset_session` when the user types ``/new``.
    """

    def __init__(self, service: Any, *, use_rag: bool = False) -> None:
        self._service = service
        self._use_rag = use_rag
        self._session_id: str | None = None

    async def _ensure_session(self) -> str:
        if self._session_id is None:
            self._session_id = await self._service.new_session()
        return self._session_id

    async def reset_session(self) -> None:
        self._session_id = await self._service.new_session()

    async def aclose(self) -> None:
        await self._service.aclose()

    async def reply(self, user_text: str, history: list[dict[str, Any]]) -> AsyncIterator[Event]:
        del history  # ChatService reads its own history from ChatMemory
        session_id = await self._ensure_session()
        async for event in self._service.generate(session_id, user_text, use_rag=self._use_rag):
            # ChatService emits plain dicts whose shape matches Event.
            yield event


async def build_default_chat_service() -> Any:
    """Build a fully wired :class:`ChatService` from global settings."""

    from core.chat_service import ChatService
    from core.knowledge.base import FileKnowledgeBase
    from core.llm.ollama import OllamaClient
    from core.memory.chat_memory import ChatMemory
    from settings import settings

    llm = OllamaClient.from_settings(settings)
    memory = ChatMemory.from_settings(settings)
    knowledge = FileKnowledgeBase.from_settings(settings) if settings.retrieval.enabled else None
    return ChatService(llm=llm, memory=memory, knowledge=knowledge)


async def build_default_provider() -> tuple[ReplyProvider, str]:
    """Return ``(provider, label)``. Falls back to echo if Ollama is unreachable."""

    from core.llm.ollama import OllamaClient
    from settings import settings

    probe = OllamaClient.from_settings(settings)
    try:
        reachable = await probe.ping()
    finally:
        await probe.aclose()

    if not reachable:
        return EchoReplyProvider(), "echo-fallback (ollama unreachable)"

    service = await build_default_chat_service()
    return (
        ChatServiceProvider(service, use_rag=settings.retrieval.enabled),
        f"ollama:{settings.ollama.chat_model}",
    )


async def run_chat(
    provider: ReplyProvider | None = None,
    model_label: str | None = None,
) -> int:
    """Interactive chat loop — the thin shell around UI + provider."""

    owned_provider = provider is None
    if provider is None:
        provider, label = await build_default_provider()
        model_label = model_label or label
    else:
        model_label = model_label or "custom-provider"

    console = make_console()
    view = ChatView(console)
    session = PromptSession()
    history: list[dict[str, Any]] = []

    view.banner(model_label)
    view.system_notice("type `/help` for commands · `/quit` to exit · `Esc+Enter` to send")

    # --- slash commands -------------------------------------------------
    from ui.prompt import SlashDispatcher

    dispatcher = SlashDispatcher()
    stop = asyncio.Event()
    # Keep strong references to background tasks so asyncio does not GC them
    # (RUF006). Tasks self-remove from the set on completion.
    pending_tasks: set[asyncio.Task[Any]] = set()

    def _quit(_: list[str]) -> None:
        stop.set()

    def _clear(_: list[str]) -> None:
        console.clear()

    def _new(_: list[str]) -> None:
        history.clear()
        if isinstance(provider, ChatServiceProvider):
            task = asyncio.create_task(provider.reset_session())
            pending_tasks.add(task)
            task.add_done_callback(pending_tasks.discard)
        view.system_notice("new session started")

    def _not_impl(name: str) -> Callable[[list[str]], None]:
        def _handler(_: list[str]) -> None:
            view.system_notice(f"`{name}` not implemented yet")

        return _handler

    def _help(_: list[str]) -> None:
        view.system_notice("commands: " + ", ".join("/" + n for n in dispatcher.registered()))

    dispatcher.register("quit", _quit)
    dispatcher.register("exit", _quit)
    dispatcher.register("clear", _clear)
    dispatcher.register("new", _new)
    dispatcher.register("model", _not_impl("/model"))
    dispatcher.register("retrieve", _not_impl("/retrieve"))
    dispatcher.register("login", _not_impl("/login"))
    dispatcher.register("logout", _not_impl("/logout"))
    dispatcher.register("help", _help)

    # --- main loop ------------------------------------------------------
    try:
        while not stop.is_set():
            try:
                line = await session.prompt_async("› ")
            except (EOFError, KeyboardInterrupt):
                view.system_notice("bye")
                return 0

            if not line.strip():
                continue

            if await dispatcher.dispatch(line):
                continue

            view.user_echo(line)
            history.append({"role": "user", "content": line})
            full = await view.stream_assistant(provider.reply(line, history))
            history.append({"role": "assistant", "content": full})

        view.system_notice("bye")
        return 0
    finally:
        if owned_provider and isinstance(provider, ChatServiceProvider):
            await provider.aclose()
