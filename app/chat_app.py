"""Orchestration layer — the one place that ties UI to the core layer.

AGENTS.md §3: ``app/`` is the only layer allowed to import both ``ui/`` and
``core/``.

Two entry points:

* :func:`run_tui_chat` — the v1.3 default. Builds a full-screen TUI with
  three panes (sidebar / transcript / input). Talks to a real Ollama if
  reachable; degrades to :class:`EchoReplyProvider` otherwise.

* :func:`run_legacy_chat` — the pre-v1.3 sequential REPL. Kept around for
  the ``--legacy`` flag and for ``tests/integration/test_cli_boot.py``
  smoke tests that can't drive a full-screen TTY.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from prompt_toolkit import prompt as _pt_prompt

from ui import ChatView, PromptSession
from ui.chat_view import Event
from ui.console import make_console

if TYPE_CHECKING:
    from core.auth.service import AuthService
    from core.chat_service import ChatService
    from core.memory.chat_memory import ChatMemory

__all__ = [
    "ChatServiceProvider",
    "EchoReplyProvider",
    "ReplyProvider",
    "TuiServices",
    "build_default_chat_service",
    "build_default_provider",
    "run_legacy_chat",
    "run_tui_chat",
]


class ReplyProvider(Protocol):
    """Contract between the orchestrator and the LLM service."""

    def reply(self, user_text: str, history: list[dict[str, Any]]) -> AsyncIterator[Event]: ...


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


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

    A ``session_id`` is minted lazily on the first call and reused across
    turns so :class:`ChatMemory` accumulates history. Switch to a different
    one with :meth:`set_session`; mint a fresh empty one with
    :meth:`reset_session`.

    ``model`` is mutable at runtime so the TUI ``/model`` command can
    swap models without rebuilding the underlying ChatService.
    """

    def __init__(
        self,
        service: ChatService,
        *,
        use_rag: bool = False,
        model: str | None = None,
    ) -> None:
        self._service = service
        self._use_rag = use_rag
        self._model = model
        self._session_id: str | None = None

    @property
    def service(self) -> ChatService:
        return self._service

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def set_model(self, model: str) -> None:
        self._model = model

    def set_session(self, session_id: str) -> None:
        self._session_id = session_id

    def set_use_rag(self, on: bool) -> None:
        self._use_rag = on

    async def _ensure_session(self) -> str:
        """Return current session_id, or attach to the most-recent one.

        Priority order:
          1. Already-set ``self._session_id`` (set by ``set_session()`` /
             previous calls within the same process).
          2. The most recently updated session from memory — so a user who
             closes the CLI and re-opens it lands back in the same
             conversation thread instead of getting a brand-new empty session.
          3. A fresh ``new_session()`` mint.

        ``/new`` and ``Ctrl+N`` explicitly bypass this by calling
        :meth:`reset_session` (which always mints).
        """
        if self._session_id is not None:
            return self._session_id
        # Try to resume.
        try:
            metas = await self._service.memory.list_session_metas()
        except Exception:
            metas = []
        if metas:
            self._session_id = metas[0].id
            return self._session_id
        self._session_id = await self._service.new_session()
        return self._session_id

    async def reset_session(self) -> str:
        self._session_id = await self._service.new_session()
        return self._session_id

    async def aclose(self) -> None:
        await self._service.aclose()

    async def reply(self, user_text: str, history: list[dict[str, Any]]) -> AsyncIterator[Event]:
        del history  # ChatService reads its own history from ChatMemory
        session_id = await self._ensure_session()
        async for event in self._service.generate(
            session_id,
            user_text,
            use_rag=self._use_rag,
            model=self._model,
        ):
            # ChatService emits plain dicts whose shape matches Event TypedDict.
            yield event  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


@dataclass
class _MemoryBundle:
    memory: ChatMemory
    label: str  # "file" | "db" | "file (db-unavailable)"
    user_id: uuid.UUID | None = None


async def _build_memory() -> _MemoryBundle:
    """Pick file vs DB based on the persisted auth token."""
    from core.memory.chat_memory import DbChatMemory, FileChatMemory
    from settings import settings

    user_id = await _resolve_local_user_id()
    if user_id is None:
        return _MemoryBundle(memory=FileChatMemory.from_settings(settings), label="file")
    try:
        from db.session import current_session_factory, init_engine

        init_engine()
        memory = DbChatMemory(session_factory=current_session_factory(), user_id=user_id)
    except Exception:
        return _MemoryBundle(
            memory=FileChatMemory.from_settings(settings),
            label="file (db-unavailable)",
        )
    return _MemoryBundle(memory=memory, label="db", user_id=user_id)


async def build_default_chat_service() -> tuple[ChatService, str, uuid.UUID | None]:
    """Build a :class:`ChatService` from global settings.

    Returns ``(service, memory_label, user_id_or_none)``.
    """
    from core.chat_service import ChatService
    from core.knowledge.base import FileKnowledgeBase
    from core.llm.ollama import OllamaClient
    from settings import settings

    llm = OllamaClient.from_settings(settings)
    knowledge = FileKnowledgeBase.from_settings(settings) if settings.retrieval.enabled else None
    bundle = await _build_memory()
    service = ChatService(llm=llm, memory=bundle.memory, knowledge=knowledge)
    return service, bundle.label, bundle.user_id


async def _resolve_local_user_id() -> uuid.UUID | None:
    """Return the ``uuid.UUID`` of the logged-in user, or ``None``."""
    from app import auth_local
    from core.auth.errors import TokenExpiredError, TokenInvalidError
    from core.auth.tokens import decode_token

    pair = auth_local.load()
    if pair is None:
        return None
    try:
        payload = decode_token(pair.access_token, expected_type="access")
    except (TokenExpiredError, TokenInvalidError):
        return None
    try:
        return uuid.UUID(payload.sub)
    except (ValueError, TypeError):
        return None


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

    service, memory_label, _ = await build_default_chat_service()
    return (
        ChatServiceProvider(service, use_rag=settings.retrieval.enabled),
        f"ollama:{settings.ollama.chat_model} · memory:{memory_label}",
    )


# ===========================================================================
# Legacy sequential mode (pre-v1.3)
# ===========================================================================


def _human(n: int) -> str:
    """Format a byte count as the largest fitting binary unit."""
    if n < 1024:
        return f"{n} B"
    units = ("KiB", "MiB", "GiB", "TiB")
    val = float(n) / 1024.0
    for unit in units:
        if val < 1024.0:
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} PiB"


async def run_legacy_chat(
    provider: ReplyProvider | None = None,
    model_label: str | None = None,
) -> int:
    """Sequential REPL with slash commands.

    Default mode (v1.4+). Commands:

      session : /sessions /switch /new /title /delete
      model   : /model [name]
      runtime : /rag on|off  /think on|off
      auth    : /register /login /logout /whoami
      misc    : /clear /help /quit
    """

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

    # Reclaim the terminal: scroll the prior shell content away so the chat
    # session feels like a dedicated workspace. Unlike the alt-screen mode
    # used by vim/htop, this leaves transcript readable after `/quit`.
    console.clear()

    view.banner(model_label)
    view.system_notice("type `/help` for commands · `/quit` to exit · `Enter` to send")

    from ui.prompt import SlashDispatcher

    dispatcher = SlashDispatcher()
    stop = asyncio.Event()
    pending_tasks: set[asyncio.Task[Any]] = set()

    def _on_unknown_command(name: str, _args: list[str]) -> None:
        """Catch typos so commands like `/ollama-ath sk-...` never leak the
        rest of the line (which often contains a secret) to the LLM."""
        suggestions = dispatcher.closest(name, n=2)
        hint = f" — did you mean /{suggestions[0]}?" if suggestions else ""
        view.error("unknown_command", f"/{name}{hint}  (type /help for a list)")

    dispatcher.set_on_unknown(_on_unknown_command)

    # ------------------------------------------------------------------
    # Shared accessors (provider may be EchoReplyProvider — feature-degraded)
    # ------------------------------------------------------------------
    def _csvc() -> ChatServiceProvider | None:
        return provider if isinstance(provider, ChatServiceProvider) else None

    def _replay_history(msgs: list[Any]) -> None:
        """Re-render past messages so the user sees what they're attaching to."""
        for m in msgs:
            if m.role == "user":
                view.user_echo(m.content)
            elif m.role == "assistant":
                view.assistant_block(m.content)
            else:
                view.system_notice(m.content)

    async def _resume_recent_session() -> None:
        """On boot: attach to the most-recent session so history persists."""
        cs = _csvc()
        if cs is None:
            return
        try:
            metas = await cs.service.memory.list_session_metas()
        except Exception:
            return
        if not metas:
            return
        sid = metas[0].id
        cs.set_session(sid)
        try:
            msgs = await cs.service.memory.get(sid)
        except Exception:
            return
        if msgs:
            view.system_notice(
                f"resumed session {sid[:8]} · {metas[0].title} · "
                f"{len(msgs)} message(s) · /new for fresh"
            )
            for m in msgs:
                history.append({"role": m.role, "content": m.content})
            _replay_history(msgs)
            view.system_notice("── end of history · type to continue ──")

    await _resume_recent_session()

    # ------------------------------------------------------------------
    # Basic commands
    # ------------------------------------------------------------------
    def _quit(_: list[str]) -> None:
        stop.set()

    def _clear(_: list[str]) -> None:
        console.clear()

    def _help(_: list[str]) -> None:
        # Grouped, opencode-style. Width-aware so it lines up on narrow ttys.
        groups: list[tuple[str, list[tuple[str, str]]]] = [
            (
                "session",
                [
                    ("/sessions [id|idx]", "list saved (with arg = jump like /switch)"),
                    ("/switch [id|idx]", "pick one (no arg = list + prompt)"),
                    ("/new [title]", "start a fresh conversation"),
                    ("/title <text>", "rename the current conversation"),
                    ("/delete", "delete the current conversation"),
                ],
            ),
            (
                "model",
                [
                    ("/model", "list pulled ollama models"),
                    ("/model <name>", "switch model at runtime"),
                    ("/model pull <name>", "download a new model from registry"),
                ],
            ),
            (
                "runtime",
                [
                    ("/rag [on|off]", "toggle retrieval-augmented context"),
                    ("/think [on|off]", "toggle deep-thinking hint (UI only)"),
                ],
            ),
            (
                "auth",
                [
                    ("/register", "create a new account"),
                    ("/login", "log in (memory switches to db on next start)"),
                    ("/logout", "log out and clear local token"),
                    ("/whoami", "show current user id"),
                    ("/ollama-auth [key|clear|show]", "set Bearer key for cloud ollama"),
                ],
            ),
            (
                "misc",
                [
                    ("/clear", "clear the screen"),
                    ("/help", "show this help"),
                    ("/quit", "exit (alias: /exit)"),
                ],
            ),
        ]
        # left column width: longest command + 2 spaces padding
        col = max(len(cmd) for _, items in groups for cmd, _ in items) + 2
        for name, items in groups:
            view.system_notice(f"── {name} ──")
            for cmd, desc in items:
                view.system_notice(f"  {cmd.ljust(col)}{desc}")
        view.system_notice("── keys ──")
        view.system_notice("  Enter       send message    Ctrl+J       insert newline")
        view.system_notice("  ↑/↓         input history   Ctrl+L       clear screen")

    # ------------------------------------------------------------------
    # Session ops
    # ------------------------------------------------------------------
    async def _sessions(args: list[str]) -> None:
        # With an arg, behave like /switch — saves users from remembering
        # which command does which when they're typing fast.
        if args:
            await _switch(args)
            return
        cs = _csvc()
        if cs is None:
            view.error("sessions", "feature unavailable in echo-fallback mode")
            return
        try:
            metas = await cs.service.memory.list_session_metas()
        except Exception as exc:
            view.error("sessions", f"{type(exc).__name__}: {exc}")
            return
        if not metas:
            view.system_notice("no sessions yet")
            return
        cur = cs.session_id
        for i, m in enumerate(metas):
            mark = "●" if m.id == cur else " "
            view.system_notice(f"{mark} [{i}] {m.id[:8]} · {m.message_count} msg · {m.title}")
        view.system_notice("tip: `/switch <idx|id>` (or `/sessions <idx|id>`) to jump")

    async def _switch(args: list[str]) -> None:
        cs = _csvc()
        if cs is None:
            view.error("switch", "feature unavailable in echo-fallback mode")
            return
        try:
            metas = await cs.service.memory.list_session_metas()
        except Exception as exc:
            view.error("switch", f"{type(exc).__name__}: {exc}")
            return
        if not metas:
            view.system_notice("no sessions yet — type a message to start one")
            return
        # No arg → list available sessions and hint at usage.
        if not args:
            cur = cs.session_id
            view.system_notice("pick one — `/switch <index>` or `/switch <id-prefix>`:")
            for i, meta in enumerate(metas):
                mark = "●" if meta.id == cur else " "
                view.system_notice(
                    f"{mark} [{i}] {meta.id[:8]} · {meta.message_count} msg · {meta.title}"
                )
            return
        # Strip help-page placeholders so a copy-paste of `/switch [1]` Just Works.
        target = args[0].strip("[]<>")
        # accept either a numeric index or an id prefix
        chosen = None
        if target.isdigit() and int(target) < len(metas):
            chosen = metas[int(target)]
        else:
            for meta in metas:
                if meta.id.startswith(target):
                    chosen = meta
                    break
        if chosen is None:
            view.error("switch", f"no session matches {target!r} — try /switch with no args")
            return
        cs.set_session(chosen.id)
        history.clear()
        try:
            msgs = await cs.service.memory.get(chosen.id)
        except Exception as exc:
            view.error("switch", f"{type(exc).__name__}: {exc}")
            return
        for msg in msgs:
            history.append({"role": msg.role, "content": msg.content})
        # Wipe whatever the previous session left on screen, redraw the
        # banner so the user knows the chat is still live, then replay the
        # newly-attached conversation.
        console.clear()
        view.banner(model_label)
        view.system_notice(f"switched to {chosen.id[:8]} · {chosen.title} · {len(msgs)} message(s)")
        _replay_history(msgs)
        view.system_notice("── end of history · type to continue ──")

    async def _new(args: list[str]) -> None:
        history.clear()
        cs = _csvc()
        if cs is None:
            view.system_notice("new session (echo mode — no persistence)")
            return
        sid = await cs.reset_session()
        if args:
            title = " ".join(args)
            try:
                await cs.service.memory.set_title(sid, title)
            except Exception as exc:
                view.error("title", f"{type(exc).__name__}: {exc}")
        view.system_notice(f"new session: {sid[:8]}")

    async def _title(args: list[str]) -> None:
        cs = _csvc()
        if cs is None or cs.session_id is None:
            view.error("title", "no current session")
            return
        if not args:
            view.error("title", "usage: /title <text>")
            return
        title = " ".join(args)
        try:
            await cs.service.memory.set_title(cs.session_id, title)
        except Exception as exc:
            view.error("title", f"{type(exc).__name__}: {exc}")
            return
        view.system_notice(f"title → {title}")

    async def _delete(_: list[str]) -> None:
        cs = _csvc()
        if cs is None or cs.session_id is None:
            view.error("delete", "no current session")
            return
        sid = cs.session_id
        try:
            await cs.service.memory.delete_session(sid)
        except Exception as exc:
            view.error("delete", f"{type(exc).__name__}: {exc}")
            return
        cs.set_session("")  # placeholder; next reply will mint a fresh session
        cs._session_id = None
        history.clear()
        view.system_notice(f"deleted {sid[:8]}")

    # ------------------------------------------------------------------
    # Model + runtime toggles
    # ------------------------------------------------------------------
    async def _model(args: list[str]) -> None:
        cs = _csvc()
        if cs is None:
            view.error("model", "feature unavailable in echo-fallback mode")
            return
        from core.llm.client import LLMError
        from core.llm.ollama import OllamaClient
        from settings import settings as _s

        # /model            → list pulled models
        # /model pull <name>→ download a new model from the registry
        # /model <name>     → switch the active model at runtime
        if args and args[0] == "pull":
            if len(args) < 2:
                view.error("model", "usage: /model pull <name>  (e.g. qwen2.5:1.5b)")
                return
            name = args[1]
            view.system_notice(f"pulling {name} … (Ctrl+C to abort)")
            client = OllamaClient.from_settings(_s)
            last_status = ""
            try:
                async for frame in client.pull_model(name):
                    if "error" in frame:
                        view.error("model", str(frame["error"]))
                        return
                    status = str(frame.get("status", ""))
                    total = frame.get("total")
                    completed = frame.get("completed")
                    if isinstance(total, int) and total > 0 and isinstance(completed, int):
                        pct = (completed / total) * 100
                        line = f"  {status} · {_human(completed)}/{_human(total)} · {pct:5.1f}%"
                    else:
                        line = f"  {status}"
                    # Stay on a single line by using rich's overwrite trick:
                    # print with end="\r" only when it's the same status as
                    # the previous frame; otherwise newline so each phase
                    # leaves a trace.
                    if status == last_status:
                        console.print(line, end="\r", soft_wrap=True, highlight=False)
                    else:
                        console.print(line, soft_wrap=True, highlight=False)
                        last_status = status
                view.system_notice(f"pulled {name} — `/model {name}` to switch")
            except LLMError as exc:
                view.error("model", str(exc))
            except KeyboardInterrupt:
                view.system_notice("pull aborted")
            finally:
                await client.aclose()
            return

        if not args:
            probe = OllamaClient.from_settings(_s)
            try:
                models = await probe.list_models()
            finally:
                await probe.aclose()
            if not models:
                view.system_notice("no models pulled — try `/model pull qwen2.5:1.5b`")
                return
            cur = cs._model or _s.ollama.chat_model
            for m in models:
                view.system_notice(("● " if m == cur else "  ") + m)
            view.system_notice("tip: `/model <name>` to switch · `/model pull <name>` to download")
            return
        cs.set_model(args[0])
        view.system_notice(f"model → {args[0]}")

    def _toggle(args: list[str], current: bool) -> bool | None:
        if not args:
            return not current
        v = args[0].lower()
        if v in ("on", "true", "1", "yes"):
            return True
        if v in ("off", "false", "0", "no"):
            return False
        return None

    rag_state = {"on": False}

    def _rag(args: list[str]) -> None:
        cs = _csvc()
        if cs is None:
            view.error("rag", "feature unavailable in echo-fallback mode")
            return
        new = _toggle(args, rag_state["on"])
        if new is None:
            view.error("rag", "usage: /rag [on|off]")
            return
        rag_state["on"] = new
        cs.set_use_rag(new)
        view.system_notice(f"rag {'on' if new else 'off'}")

    think_state = {"on": False}

    def _think(args: list[str]) -> None:
        new = _toggle(args, think_state["on"])
        if new is None:
            view.error("think", "usage: /think [on|off]")
            return
        think_state["on"] = new
        # Currently a UI-only flag; chat_service does not yet thread it.
        view.system_notice(f"think {'on' if new else 'off'} (note: not yet wired to LLM)")

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    auth_state: dict[str, Any] = {"service": None}

    async def _auth_service() -> AuthService:
        svc = auth_state["service"]
        if svc is not None:
            return svc  # type: ignore[no-any-return]
        from core.auth.service import AuthService
        from db.session import current_session_factory, init_engine

        init_engine()
        svc = AuthService(current_session_factory())
        auth_state["service"] = svc
        return svc

    async def _ask(prompt: str, *, password: bool = False) -> str:
        return await asyncio.to_thread(_pt_prompt, prompt, is_password=password)

    async def _register(_args: list[str]) -> None:
        from core.auth.errors import AuthError, EmailAlreadyExistsError

        email = (await _ask("email: ")).strip()
        if not email:
            view.error("register", "empty email")
            return
        password = await _ask("password (min 8, letter+digit): ", password=True)
        confirm = await _ask("confirm: ", password=True)
        if password != confirm:
            view.error("register", "passwords don't match")
            return
        display = (await _ask("display name (optional): ")).strip() or None
        try:
            svc = await _auth_service()
            user = await svc.register(email, password, display_name=display)
        except EmailAlreadyExistsError:
            view.error("register", "email already registered, try /login")
            return
        except AuthError as exc:
            view.error("register", str(exc) or "registration failed")
            return
        except Exception as exc:
            view.error("auth_unavailable", f"{type(exc).__name__}: {exc}")
            return
        view.system_notice(f"registered {user.email}; now /login")

    async def _login(_args: list[str]) -> None:
        from app import auth_local
        from core.auth.errors import AuthError

        email = (await _ask("email: ")).strip()
        if not email:
            view.error("login_cancelled", "empty email")
            return
        password = await _ask("password: ", password=True)
        try:
            service = await _auth_service()
            pair = await service.login(email, password)
        except AuthError as exc:
            view.error(type(exc).__name__, str(exc) or "authentication failed")
            return
        except Exception as exc:
            view.error("auth_unavailable", f"{type(exc).__name__}: {exc}")
            return
        auth_local.save(pair)
        view.system_notice(f"logged in as {email} — restart CLI to switch memory to db")

    async def _logout(_args: list[str]) -> None:
        from app import auth_local

        pair = auth_local.load()
        if pair is None:
            view.system_notice("not logged in")
            return
        try:
            service = await _auth_service()
            await service.logout(pair.refresh_token)
        except Exception as exc:
            view.system_notice(f"remote logout failed ({type(exc).__name__}); clearing local token")
            del exc
        auth_local.clear()
        view.system_notice("logged out — restart CLI to switch memory to file")

    def _whoami(_: list[str]) -> None:
        from app import auth_local
        from core.auth.errors import TokenExpiredError, TokenInvalidError
        from core.auth.tokens import decode_token

        pair = auth_local.load()
        if pair is None:
            view.system_notice("not logged in")
            return
        try:
            payload = decode_token(pair.access_token, expected_type="access")
        except TokenExpiredError:
            view.system_notice("session expired — please /login again")
            return
        except TokenInvalidError as exc:
            view.error("token_invalid", str(exc))
            return
        view.system_notice(f"user_id={payload.sub}")

    async def _ollama_auth(args: list[str]) -> None:
        """Configure Bearer auth for hosted/proxied Ollama (e.g. cloud).

        Usage:
          /ollama-auth              → prompt for key (hidden input)
          /ollama-auth <key>        → set inline (avoid in shared terminals)
          /ollama-auth clear        → drop the key
          /ollama-auth show         → print masked current key
        """
        from core.llm.ollama import OllamaClient
        from settings import settings as _s

        cur = _s.ollama.api_key
        if args and args[0] == "show":
            if cur:
                masked = cur[:4] + "…" + cur[-4:] if len(cur) > 12 else "***"
                view.system_notice(f"ollama api_key: {masked}")
            else:
                view.system_notice("ollama api_key: (not set)")
            return
        if args and args[0] == "clear":
            new_value: str | None = None
        elif args:
            new_value = args[0]
        else:
            entered = (await _ask("ollama api key: ", password=True)).strip()
            if not entered:
                view.error("ollama-auth", "empty key")
                return
            new_value = entered
        # Update both the global settings (so future from_settings() picks it up)
        # AND the live LLM client of the current provider (so the very next
        # message uses it without restarting).
        _s.ollama.api_key = new_value
        cs = _csvc()
        if cs is not None:
            llm = cs.service.llm
            if isinstance(llm, OllamaClient):
                await llm.set_api_key(new_value)
        if new_value is None:
            view.system_notice("ollama api_key cleared (this process only)")
        else:
            view.system_notice(
                "ollama api_key set for this session. "
                "To persist, add `OLLAMA_API_KEY=<key>` to .env"
            )

    # ------------------------------------------------------------------
    # Register
    # ------------------------------------------------------------------
    dispatcher.register("quit", _quit)
    dispatcher.register("exit", _quit)
    dispatcher.register("clear", _clear)
    dispatcher.register("help", _help)
    dispatcher.register("sessions", _sessions)
    dispatcher.register("switch", _switch)
    dispatcher.register("new", _new)
    dispatcher.register("title", _title)
    dispatcher.register("delete", _delete)
    dispatcher.register("model", _model)
    dispatcher.register("rag", _rag)
    dispatcher.register("think", _think)
    dispatcher.register("register", _register)
    dispatcher.register("login", _login)
    dispatcher.register("logout", _logout)
    dispatcher.register("whoami", _whoami)
    dispatcher.register("ollama-auth", _ollama_auth)
    # silence pending_tasks unused warning (kept for future async slash work)
    del pending_tasks

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


# ===========================================================================
# v1.3 TUI mode
# ===========================================================================


@dataclass
class TuiServices:
    """Bag of dependencies passed into ``ui/commands.py`` handlers.

    Each callable does the actual work; the command handler in
    :mod:`ui.commands` only orchestrates UI state and delegates here. This
    keeps ``ui/commands.py`` free of any DB / LLM imports and keeps this
    module the single seam between presentation and core/db.
    """

    # mutable runtime
    provider: ChatServiceProvider | None
    memory: ChatMemory

    # registry — set after construction so /help can list commands
    command_registry: object | None = None

    # callbacks (populated by run_tui_chat)
    set_provider_model: Callable[[str], None] = field(default=lambda _m: None)
    do_register: Callable[[], Awaitable[None]] = field(default=lambda: _noop())
    do_login: Callable[[], Awaitable[None]] = field(default=lambda: _noop())
    do_logout: Callable[[], Awaitable[None]] = field(default=lambda: _noop())
    do_new_session: Callable[[str | None], Awaitable[None]] = field(default=lambda _t: _noop())
    do_switch_session: Callable[[str], Awaitable[None]] = field(default=lambda _s: _noop())
    do_set_current_title: Callable[[str], Awaitable[None]] = field(default=lambda _t: _noop())
    do_delete_current: Callable[[], Awaitable[None]] = field(default=lambda: _noop())
    do_refresh_sessions: Callable[[], Awaitable[None]] = field(default=lambda: _noop())


async def _noop() -> None:
    return None


async def run_tui_chat() -> int:
    """Full-screen three-pane TUI. Returns process exit code."""

    from core.auth.errors import (
        AuthError,
        EmailAlreadyExistsError,
    )
    from core.auth.tokens import decode_token
    from core.llm.ollama import OllamaClient
    from settings import settings
    from ui.app import build_application
    from ui.commands import CommandContext, CommandRegistry, register_default_commands
    from ui.state import SessionRow, TuiState
    from ui.transcript import TranscriptBuffer

    # --- Build core layer -------------------------------------------------
    state = TuiState(current_model=settings.ollama.chat_model)
    transcript = TranscriptBuffer()

    probe = OllamaClient.from_settings(settings)
    reachable = False
    try:
        reachable = await probe.ping()
        if reachable:
            state.available_models = await probe.list_models()
            if state.available_models and state.current_model not in state.available_models:
                fallback = state.available_models[0]
                transcript.add_system(
                    f"model {state.current_model!r} not pulled; using {fallback!r}"
                )
                state.current_model = fallback
    finally:
        await probe.aclose()

    if reachable:
        service, memory_label, user_id = await build_default_chat_service()
        provider: ChatServiceProvider | None = ChatServiceProvider(
            service,
            use_rag=settings.retrieval.enabled,
            model=state.current_model,
        )
        state.memory_mode = memory_label  # type: ignore[assignment]
        if user_id is not None:
            from app import auth_local

            pair = auth_local.load()
            if pair is not None:
                try:
                    decode_token(pair.access_token, expected_type="access")
                    # We don't have the email handy; show user_id prefix instead.
                    state.user_email = f"user:{str(user_id)[:8]}"
                except Exception:  # noqa: S110 — best-effort label only, no security impact
                    pass
        memory = service.memory
    else:
        provider = None
        from core.memory.chat_memory import FileChatMemory

        memory = FileChatMemory.from_settings(settings)
        state.memory_mode = "file"
        transcript.add_error("ollama", "server unreachable; chat disabled. Try `ollama serve`.")

    # --- Sidebar bootstrap -----------------------------------------------
    async def _refresh_sessions() -> None:
        metas = await memory.list_session_metas()
        state.sessions = [
            SessionRow(id=m.id, title=m.title, message_count=m.message_count) for m in metas
        ]
        # Anchor cursor to current session if present.
        if state.current_session_id:
            for i, row in enumerate(state.sessions):
                if row.id == state.current_session_id:
                    state.sidebar_cursor = i
                    break

    await _refresh_sessions()

    # --- Resume the most-recent session on boot -------------------------
    # So a user who exits the CLI and re-opens it lands back in the same
    # conversation thread (sidebar shows them, transcript replays history,
    # next message appends to the same JSON / DB row instead of forking
    # off into a brand-new empty session). Skipped when there's no
    # provider (ollama unreachable) or no prior sessions.
    if provider is not None and state.sessions:
        first = state.sessions[0]
        provider.set_session(first.id)
        state.current_session_id = first.id
        try:
            history = await memory.get(first.id)
            for m in history:
                if m.role == "user":
                    transcript.add_user(m.content)
                elif m.role == "assistant":
                    transcript.start_assistant()
                    transcript.append_to_assistant(m.content)
                    transcript.end_assistant()
                else:
                    transcript.add_system(m.content)
        except Exception as exc:
            transcript.add_error("resume_failed", f"{type(exc).__name__}: {exc}")

    # --- Auth helpers -----------------------------------------------------
    auth_state: dict[str, Any] = {"service": None}

    async def _auth_service() -> AuthService:
        svc = auth_state["service"]
        if svc is not None:
            return svc  # type: ignore[no-any-return]
        from core.auth.service import AuthService
        from db.session import current_session_factory, init_engine

        init_engine()
        svc = AuthService(current_session_factory())
        auth_state["service"] = svc
        return svc

    async def _ask(prompt: str, *, password: bool = False) -> str:
        return await asyncio.to_thread(_pt_prompt, prompt, is_password=password)

    async def _do_register() -> None:
        try:
            email = (await _ask("email: ")).strip()
            if not email:
                transcript.add_error("register", "empty email")
                return
            password = await _ask("password (min 8, letter+digit): ", password=True)
            confirm = await _ask("confirm: ", password=True)
            if password != confirm:
                transcript.add_error("register", "passwords don't match")
                return
            display_name = (await _ask("display name (optional): ")).strip() or None
            try:
                svc = await _auth_service()
                user = await svc.register(email, password, display_name=display_name)
            except EmailAlreadyExistsError:
                transcript.add_error("register", "email already registered, try /login")
                return
            except AuthError as exc:
                transcript.add_error("register", str(exc) or "registration failed")
                return
            transcript.add_system(f"registered as {user.email}; now run /login")
        except Exception as exc:
            transcript.add_error("auth_unavailable", f"{type(exc).__name__}: {exc}")

    async def _do_login() -> None:
        from app import auth_local

        try:
            email = (await _ask("email: ")).strip()
            if not email:
                transcript.add_error("login", "empty email")
                return
            password = await _ask("password: ", password=True)
            try:
                svc = await _auth_service()
                pair = await svc.login(email, password)
            except AuthError as exc:
                transcript.add_error(type(exc).__name__, str(exc) or "authentication failed")
                return
            auth_local.save(pair)
            state.user_email = email
            transcript.add_system(f"logged in as {email} — restart CLI to switch memory to db")
        except Exception as exc:
            transcript.add_error("auth_unavailable", f"{type(exc).__name__}: {exc}")

    async def _do_logout() -> None:
        from app import auth_local

        pair = auth_local.load()
        if pair is None:
            transcript.add_system("not logged in")
            return
        try:
            svc = await _auth_service()
            await svc.logout(pair.refresh_token)
        except Exception as exc:
            transcript.add_system(
                f"remote logout failed ({type(exc).__name__}); clearing local token"
            )
        auth_local.clear()
        state.user_email = None
        transcript.add_system("logged out — restart CLI to switch memory to file")

    # --- Session ops ------------------------------------------------------
    async def _do_new_session(title: str | None) -> None:
        if provider is None:
            transcript.add_error("new", "no active provider (ollama unreachable)")
            return
        sid = await provider.reset_session()
        if title:
            await memory.set_title(sid, title)
        state.current_session_id = sid
        await _refresh_sessions()
        transcript.add_system(f"new session: {title or sid[:8]}")

    async def _do_switch_session(sid: str) -> None:
        if provider is None:
            transcript.add_error("switch", "no active provider")
            return
        # Replay history into the transcript pane.
        try:
            msgs = await memory.get(sid)
        except Exception as exc:
            transcript.add_error("switch", f"{type(exc).__name__}: {exc}")
            return
        provider.set_session(sid)
        state.current_session_id = sid
        transcript.clear()
        for m in msgs:
            if m.role == "user":
                transcript.add_user(m.content)
            elif m.role == "assistant":
                transcript.start_assistant()
                transcript.append_to_assistant(m.content)
                transcript.end_assistant()
            else:
                transcript.add_system(m.content)
        await _refresh_sessions()

    async def _do_set_title(title: str) -> None:
        if state.current_session_id is None:
            transcript.add_error("title", "no current session")
            return
        await memory.set_title(state.current_session_id, title)
        await _refresh_sessions()
        transcript.add_system(f"title → {title}")

    async def _do_delete_current() -> None:
        sid = state.current_session_id
        if sid is None:
            row = state.session_at_cursor()
            sid = row.id if row else None
        if sid is None:
            transcript.add_error("delete", "no session selected")
            return
        await memory.delete_session(sid)
        if provider is not None and provider.session_id == sid:
            # Drop the in-memory pointer so the next reply mints a fresh one.
            provider._session_id = None
        if state.current_session_id == sid:
            state.current_session_id = None
            transcript.clear()
        await _refresh_sessions()
        transcript.add_system(f"deleted {sid[:8]}")

    def _set_provider_model(name: str) -> None:
        if provider is not None:
            provider.set_model(name)

    services = TuiServices(
        provider=provider,
        memory=memory,
        set_provider_model=_set_provider_model,
        do_register=_do_register,
        do_login=_do_login,
        do_logout=_do_logout,
        do_new_session=_do_new_session,
        do_switch_session=_do_switch_session,
        do_set_current_title=_do_set_title,
        do_delete_current=_do_delete_current,
        do_refresh_sessions=_refresh_sessions,
    )

    registry = CommandRegistry()
    register_default_commands(registry)
    services.command_registry = registry

    cmd_ctx = CommandContext(state=state, transcript=transcript, services=services)

    # --- Send pipeline ----------------------------------------------------
    async def _on_send(text: str) -> None:
        if text.startswith("/"):
            await registry.dispatch(cmd_ctx, text)
            return
        if provider is None:
            transcript.add_error("chat", "no active provider")
            return
        transcript.add_user(text)
        transcript.start_assistant()
        try:
            async for evt in provider.reply(text, []):
                etype = evt.get("type")
                if etype == "token":
                    transcript.append_to_assistant(evt.get("delta", ""))
                elif etype == "retrieval":
                    hits = evt.get("hits") or []
                    if hits:  # silence empty retrieval events (RAG off / no hits)
                        transcript.add_system(f"retrieved {len(hits)} chunk(s)")
                elif etype == "done":
                    transcript.end_assistant(duration_ms=evt.get("duration_ms"))
                elif etype == "error":
                    transcript.add_error(evt.get("code", "error"), evt.get("message", ""))
        except Exception as exc:
            transcript.add_error("unexpected", f"{type(exc).__name__}: {exc}")
        # Sidebar may have a new session row + bumped count.
        await _refresh_sessions()
        if provider.session_id is not None and state.current_session_id != provider.session_id:
            state.current_session_id = provider.session_id

    async def _on_switch(sid: str) -> None:
        await _do_switch_session(sid)

    async def _on_new() -> None:
        await _do_new_session(None)

    async def _on_delete() -> None:
        await _do_delete_current()

    # --- Run --------------------------------------------------------------
    app = build_application(
        state,
        transcript,
        on_send=_on_send,
        on_switch=_on_switch,
        on_new_session=_on_new,
        on_delete_current=_on_delete,
    )

    # ---- Welcome / quick-start ------------------------------------------
    transcript.add_system(
        f"rag-chat · ollama:{state.current_model} · memory:{state.memory_mode} · ready"
    )
    transcript.add_system("─── quick-start ───────────────────────────────────────")
    if state.user_email is None:
        transcript.add_system(
            "  not logged in — type /register or /login (memory uses local files)"
        )
    else:
        transcript.add_system(f"  logged in as {state.user_email} (memory: {state.memory_mode})")
    transcript.add_system("  /help        all commands")
    transcript.add_system("  /model       list / switch ollama models")
    transcript.add_system("  /new [title] start a new conversation")
    transcript.add_system("  /switch <id> jump to a session (or Tab → ↑↓ → Enter on sidebar)")
    transcript.add_system("  Enter        send message · Alt+Enter newline")
    transcript.add_system("  Ctrl+P/N     scroll 1 line · Ctrl+U/F half page · Home/End top/bottom")
    transcript.add_system("  (macOS Terminal eats PgUp/PgDn — use Ctrl+P/N instead)")
    transcript.add_system("  Ctrl+R rag · Ctrl+T think · Ctrl+B sidebar · Ctrl+Q quit")
    transcript.add_system("───────────────────────────────────────────────────────")

    try:
        await app.run_async()
    finally:
        if provider is not None:
            await provider.aclose()
    return 0
