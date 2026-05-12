"""Orchestration layer — the one place that ties UI to the core layer.

AGENTS.md §3: ``app/`` is the only layer allowed to import both ``ui/`` and
``core/``.

Single entry point :func:`run_legacy_chat` — sequential REPL with slash
commands. The v1.3 full-screen TUI was removed in P0 cleanup (see
openspec/changes/add-tui-three-pane-layout — abandoned).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from prompt_toolkit import prompt as _pt_prompt

from core.streaming.events import Event
from ui import ChatView, PromptSession
from ui.console import make_console

if TYPE_CHECKING:
    from core.auth.service import AuthService
    from core.chat_service import ChatService
    from core.memory.chat_memory import ChatMemory

__all__ = [
    "ChatServiceProvider",
    "build_default_chat_service",
    "build_default_provider",
    "run_legacy_chat",
]


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class ChatServiceProvider:
    """Stateful REPL adapter on top of :class:`core.chat_service.ChatService`.

    A ``session_id`` is minted lazily on the first call and reused across
    turns so :class:`ChatMemory` accumulates history. Switch to a different
    one with :meth:`set_session`; mint a fresh empty one with
    :meth:`reset_session`.

    ``model`` is mutable at runtime so the ``/model`` command can swap
    models without rebuilding the underlying ChatService.
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
            # ChatService now emits ``core.streaming.events.Event`` directly.
            yield event


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

    Knowledge base wiring:
    * No DB / no user — :class:`FileKnowledgeBase` stub (returns no hits).
    * DB reachable + user — :class:`PgvectorKnowledgeBase` scoped to user.
    """
    from core.chat_service import ChatService
    from core.knowledge import FileKnowledgeBase, KnowledgeBase, PgvectorKnowledgeBase
    from core.llm.ollama import OllamaClient
    from settings import settings

    llm = OllamaClient.from_settings(settings)
    bundle = await _build_memory()

    knowledge: KnowledgeBase | None
    if not settings.retrieval.enabled:
        knowledge = None
    elif bundle.user_id is not None and bundle.label.startswith("db"):
        from db.session import current_session_factory

        knowledge = PgvectorKnowledgeBase.from_settings(
            session_factory=current_session_factory(),
            llm=llm,
            user_id=bundle.user_id,
            s=settings,
        )
    else:
        # Logged-out path: real on-disk KB at ~/.config/rag-chat/kb/.
        # Same LLM client is reused for query embedding so the embed model
        # stays consistent with whatever the user is running in Ollama.
        knowledge = FileKnowledgeBase.from_settings(llm=llm, s=settings)

    service = ChatService(llm=llm, memory=bundle.memory, knowledge=knowledge)
    return service, bundle.label, bundle.user_id


async def _resolve_local_user_id() -> uuid.UUID | None:
    """Return the ``uuid.UUID`` of the logged-in user, or ``None``.

    Refresh flow: the access token TTL is short (15 min by default), so
    re-opening the CLI after a coffee break would land in a logged-out
    state if we only checked the access token. We instead:

      1. Try to decode the access token.
      2. If expired, attempt a refresh via :class:`AuthService` using the
         stored refresh token (TTL 7 days). On success, persist the new
         pair to ``token.json`` so subsequent runs stay logged in.
      3. If both tokens are dead (refresh expired / revoked / DB
         unreachable), return ``None`` — caller falls back to logged-out.
    """
    from app import auth_local
    from core.auth.errors import TokenExpiredError, TokenInvalidError
    from core.auth.tokens import decode_token

    pair = auth_local.load()
    if pair is None:
        return None
    # Happy path: access token is still valid.
    try:
        payload = decode_token(pair.access_token, expected_type="access")
        return uuid.UUID(payload.sub)
    except TokenExpiredError:
        pass  # try refresh below
    except TokenInvalidError:
        # Tampered, malformed, or signed with a different JWT_SECRET.
        # Refresh can't help here — wipe the bad token and treat as
        # logged out so the user gets a clear /login prompt rather than
        # silent confusion.
        auth_local.clear()
        return None
    except (ValueError, TypeError):
        return None

    # Access token expired → try to refresh.
    try:
        from core.auth.service import AuthService
        from db.session import current_session_factory, init_engine

        init_engine()
        auth_svc = AuthService(session_factory=current_session_factory())
        new_pair = await auth_svc.refresh(pair.refresh_token)
    except (TokenExpiredError, TokenInvalidError):
        # Refresh token also dead — full re-login required. Drop the
        # stale file so /whoami / /login behave predictably.
        auth_local.clear()
        return None
    except Exception:
        # DB unreachable, user deactivated, reuse detected, etc.
        # Stay quiet — caller sees user_id=None and goes logged-out.
        return None

    auth_local.save(new_pair)
    try:
        payload = decode_token(new_pair.access_token, expected_type="access")
        return uuid.UUID(payload.sub)
    except (TokenExpiredError, TokenInvalidError, ValueError, TypeError):
        return None


async def build_default_provider() -> tuple[ChatServiceProvider, str]:
    """Return ``(provider, label)``. Fail-fast (SystemExit) if Ollama is unreachable.

    P0.5 collapse removed the echo fallback — see openspec/changes archive
    and ``memory/project_collapse_decisions.md``.
    """
    from core.llm.ollama import OllamaClient
    from settings import settings

    probe = OllamaClient.from_settings(settings)
    try:
        reachable = await probe.ping()
    finally:
        await probe.aclose()

    if not reachable:
        raise SystemExit(
            f"ollama unreachable at {settings.ollama.base_url} — "
            "start it (e.g. `docker compose up ollama` or `ollama serve`) "
            "or set OLLAMA_BASE_URL to a reachable endpoint."
        )

    service, memory_label, _ = await build_default_chat_service()
    return (
        ChatServiceProvider(service, use_rag=settings.retrieval.enabled),
        f"ollama:{settings.ollama.chat_model} · memory:{memory_label}",
    )


# ===========================================================================
# Legacy sequential mode (pre-v1.3)
# ===========================================================================


# Slash command catalog. Single source of truth — used by both ``/help``
# (rendered as a Rich panel) and the prompt_toolkit completer (popup menu
# when the user types ``/``). Keep names *without* leading slashes here;
# the UI layer adds the slash when displaying.
#
# Aliases (e.g. ``exit`` for ``quit``) are intentionally omitted from this
# list to keep the completer menu uncluttered; they still work at dispatch
# time because each alias is ``register()``-ed separately below.
_COMMAND_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "session",
        [
            ("sessions [id|idx]", "list saved (with arg = jump like /switch)"),
            ("switch [id|idx]", "pick one (no arg = list + prompt)"),
            ("new [title]", "start a fresh conversation"),
            ("title <text>", "rename the current conversation"),
            ("delete", "delete the current conversation"),
        ],
    ),
    (
        "model",
        [
            ("model", "list pulled ollama models"),
            ("model <name>", "switch model at runtime"),
            ("model pull <name>", "download a new model from registry"),
        ],
    ),
    (
        "runtime",
        [
            ("rag [on|off]", "toggle retrieval-augmented context"),
            ("think [on|off]", "toggle deep-thinking hint (UI only)"),
        ],
    ),
    (
        "knowledge",
        [
            ("kb", "knowledge base summary"),
            ("kb list", "list documents in the active KB"),
            ("kb show <idx|id>", "show document metadata + first chunks"),
            ("kb search <query>", "preview retrieval (no LLM call)"),
            ("kb delete <idx|id>", "delete a document and its chunks"),
            ("kb sync", "push local KB into pgvector (logged-in only)"),
            ("save [title]", "persist last Q+A turn into the active KB"),
            ("reflect [on|off|<0..1>]", "auto-save high-quality turns (with threshold)"),
        ],
    ),
    (
        "auth",
        [
            ("register", "create a new account"),
            ("login", "log in (memory switches to db on next start)"),
            ("logout", "log out and clear local token"),
            ("whoami", "show current user id"),
            ("ollama-auth [key|clear|show]", "set Bearer key for cloud ollama"),
        ],
    ),
    (
        "misc",
        [
            ("clear", "clear the screen"),
            ("help", "show this help"),
            ("quit", "exit (alias: /exit)"),
        ],
    ),
]

_KEY_HINTS: list[tuple[str, str]] = [
    ("Enter", "send message"),
    ("Ctrl+J", "insert newline"),
    ("Tab", "complete slash command"),
    ("↑ / ↓", "input history (or navigate completion menu)"),
    ("Ctrl+L", "clear screen"),
]


def _completer_specs() -> list[tuple[str, str]]:
    """Flatten :data:`_COMMAND_GROUPS` for the prompt_toolkit completer.

    The completer matches against the *bare name* (before the first
    space in the help signature), so ``("sessions [id|idx]", "...")``
    becomes ``("sessions", "...")``. Without this, typing ``/sessio``
    would fail to match because ``"sessions [id|idx]".startswith("sessio")``
    is true but tab-completing would insert ``sessions [id|idx]``.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for _section, items in _COMMAND_GROUPS:
        for cmd, desc in items:
            name = cmd.split(" ", 1)[0]
            if name in seen:
                continue
            seen.add(name)
            out.append((name, desc))
    return out


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
    provider: ChatServiceProvider | None = None,
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
    session = PromptSession(commands_provider=_completer_specs)
    history: list[dict[str, Any]] = []
    # Last completed (user, assistant) pair — drives /save and the
    # auto-reflect critic. Lifted up here (instead of next to /save's
    # handler) so :func:`_resume_recent_session` can seed it from a
    # restored session's tail. Without this seed, /save right after
    # ``make dev.cli`` boot reports "no completed turn yet" even though
    # the screen shows the resumed conversation.
    last_turn: dict[str, str] = {"user": "", "assistant": ""}

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
    # Shared accessor — provider is always a ChatServiceProvider post-P0.5.
    # The Optional return type and ``if cs is None`` guards in call sites
    # below are dead defensive code; left in place to keep this collapse
    # commit small. A follow-up task can prune them.
    # ------------------------------------------------------------------
    def _csvc() -> ChatServiceProvider | None:
        return provider

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
            # Seed last_turn from the tail so /save right after resume
            # targets the just-replayed exchange. We walk the list in
            # reverse looking for an ``assistant`` message and the
            # nearest preceding ``user`` message; tool / system turns
            # are skipped because /save persists the human-readable
            # Q+A pair, not internal scratch.
            last_asst: str | None = None
            last_user: str | None = None
            for m in reversed(msgs):
                if last_asst is None and m.role == "assistant":
                    last_asst = m.content
                    continue
                if last_asst is not None and m.role == "user":
                    last_user = m.content
                    break
            if last_user and last_asst:
                last_turn["user"] = last_user
                last_turn["assistant"] = last_asst
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
        # Single-frame Rich panel — see ChatView.help_panel.
        # Prepend ``/`` to command signatures for the rendered output;
        # the catalog stores bare names so the completer can match
        # against typed prefix without stripping.
        display_groups: list[tuple[str, list[tuple[str, str]]]] = [
            (section, [(f"/{cmd}", desc) for cmd, desc in items])
            for section, items in _COMMAND_GROUPS
        ]
        view.help_panel(display_groups, _KEY_HINTS)

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
    # /kb — knowledge base inspection
    #
    # Operates against the active ChatService.knowledge — either
    # FileKnowledgeBase (logged-out, on-disk JSONL) or
    # PgvectorKnowledgeBase (logged-in, Postgres). Both impls expose the
    # same admin API (add_document / list_documents / get_document /
    # delete_document) so the slash commands don't branch on type.
    #
    # Short-circuits with a friendly message when knowledge is None
    # (RAG disabled in settings).
    # ------------------------------------------------------------------
    def _resolve_idx_or_id(arg: str, docs: list[Any]) -> Any | None:
        """Look up a doc by numeric index (``[N]``) or id prefix.

        Accepts the full UUID hex or any unique prefix ≥ 4 chars.
        Returns ``None`` when nothing matches or when a prefix is
        ambiguous — caller renders the error.
        """
        if not docs:
            return None
        if arg.isdigit():
            i = int(arg)
            if 0 <= i < len(docs):
                return docs[i]
            return None
        if len(arg) < 4:
            return None
        matches = [d for d in docs if d.id.startswith(arg)]
        if len(matches) == 1:
            return matches[0]
        return None

    async def _kb_admin() -> Any:
        """Return the active admin-capable KB or ``None`` (with notice).

        Both ``FileKnowledgeBase`` and ``PgvectorKnowledgeBase`` now
        implement the admin surface (#34), so this only filters out the
        ``None`` (RAG disabled) case. Renamed from ``_kb_local`` since
        "local" no longer captures what we accept.
        """
        cs = _csvc()
        if cs is None:
            view.error("kb", "feature unavailable (no chat service)")
            return None
        kb = cs.service.knowledge
        if kb is None:
            view.error("kb", "RAG is disabled (set RETRIEVAL_ENABLED=true)")
            return None
        return kb

    def _kb_label(kb: Any) -> str:
        """Short ``local|pgvector`` tag for status lines."""
        from core.knowledge import FileKnowledgeBase, PgvectorKnowledgeBase

        if isinstance(kb, FileKnowledgeBase):
            return "local"
        if isinstance(kb, PgvectorKnowledgeBase):
            return "pgvector"
        return type(kb).__name__

    def _kb_root_hint(kb: Any) -> str:
        """Right-hand status hint for KB summary lines."""
        from core.knowledge import FileKnowledgeBase

        if isinstance(kb, FileKnowledgeBase):
            return f"root: {kb.root}"
        return f"backend: {_kb_label(kb)}"

    async def _kb_list(_args: list[str]) -> None:
        kb = await _kb_admin()
        if kb is None:
            return
        docs = await kb.list_documents()
        label = _kb_label(kb)
        if not docs:
            view.system_notice(f"{label} kb empty · {_kb_root_hint(kb)}")
            return
        from rich.table import Table

        t = Table(
            title=f"{label} kb · {len(docs)} document(s) · {_kb_root_hint(kb)}",
            title_style="bold",
            header_style="bold",
            border_style="grey37",
            padding=(0, 1),
        )
        t.add_column("#", justify="right", style="grey50")
        t.add_column("id", style="dim", no_wrap=True)
        t.add_column("title")
        t.add_column("chunks", justify="right")
        t.add_column("chars", justify="right")
        t.add_column("tags", style="dim")
        for i, d in enumerate(docs):
            t.add_row(
                str(i),
                d.id[:8],
                d.title or "(untitled)",
                str(d.chunk_count),
                _human(d.char_count),
                ", ".join(d.tags) if d.tags else "",
            )
        view.console.print(t)

    async def _kb_show(args: list[str]) -> None:
        if not args:
            view.error("kb", "usage: /kb show <idx|id>")
            return
        kb = await _kb_admin()
        if kb is None:
            return
        docs = await kb.list_documents()
        doc = _resolve_idx_or_id(args[0], docs)
        if doc is None:
            view.error("kb", f"no document matching {args[0]!r}")
            return
        result = await kb.get_document(doc.id, max_chunks=3)
        if result is None:
            view.error("kb", f"document {doc.id[:8]} not found")
            return
        info, chunks = result
        view.system_notice(
            f"{info.id[:8]} · {info.title} · chunks={info.chunk_count} · "
            f"chars={_human(info.char_count)}"
        )
        view.system_notice(
            f"source: {info.source}  ·  created: {info.created_at[:19]}"
            + (f"  ·  tags: {', '.join(info.tags)}" if info.tags else "")
        )
        for idx, content in chunks:
            preview = content if len(content) <= 240 else content[:237] + "…"
            view.system_notice(f"[{idx}] {preview}")
        if info.chunk_count > len(chunks):
            view.system_notice(
                f"… {info.chunk_count - len(chunks)} more chunk(s) hidden"
            )

    async def _kb_search(args: list[str]) -> None:
        if not args:
            view.error("kb", "usage: /kb search <query>")
            return
        kb = await _kb_admin()
        if kb is None:
            return
        from settings import settings as _s

        query = " ".join(args)
        try:
            hits = await kb.search(query, top_k=int(_s.retrieval.top_k))
        except Exception as exc:
            view.error("kb", f"{type(exc).__name__}: {exc}")
            return
        if not hits:
            view.system_notice(f"no hits for {query!r}")
            return
        view.system_notice(f"{len(hits)} hit(s) for {query!r}")
        for i, h in enumerate(hits, start=1):
            preview = h.content if len(h.content) <= 200 else h.content[:197] + "…"
            view.system_notice(f"[{i}] {h.score:.3f} · {h.title} · {preview}")

    async def _kb_delete(args: list[str]) -> None:
        if not args:
            view.error("kb", "usage: /kb delete <idx|id>")
            return
        kb = await _kb_admin()
        if kb is None:
            return
        docs = await kb.list_documents()
        doc = _resolve_idx_or_id(args[0], docs)
        if doc is None:
            view.error("kb", f"no document matching {args[0]!r}")
            return
        # Confirm via prompt so a misclick doesn't nuke a doc.
        try:
            confirm = await asyncio.get_event_loop().run_in_executor(
                None,
                _pt_prompt,
                f"delete '{doc.title}' ({doc.id[:8]}, {doc.chunk_count} chunks)? [y/N] ",
            )
        except (EOFError, KeyboardInterrupt):
            view.system_notice("delete cancelled")
            return
        if confirm.strip().lower() not in {"y", "yes"}:
            view.system_notice("delete cancelled")
            return
        ok = await kb.delete_document(doc.id)
        if ok:
            view.system_notice(f"deleted {doc.id[:8]} · {doc.title}")
        else:
            view.error("kb", f"document {doc.id[:8]} not found (concurrent delete?)")

    async def _kb_summary() -> None:
        kb = await _kb_admin()
        if kb is None:
            return
        docs = await kb.list_documents()
        label = _kb_label(kb)
        if not docs:
            view.system_notice(f"{label} kb empty · {_kb_root_hint(kb)}")
            view.system_notice(
                "tip: /save after a good Q+A to start filling it, or `main ingest`"
            )
            return
        total_chunks = sum(d.chunk_count for d in docs)
        total_chars = sum(d.char_count for d in docs)
        view.system_notice(
            f"{label} kb · {len(docs)} doc(s) · {total_chunks} chunk(s) · "
            f"{_human(total_chars)} · {_kb_root_hint(kb)}"
        )
        view.system_notice("recent:")
        for i, d in enumerate(docs[-5:]):
            view.system_notice(f"  [{i}] {d.id[:8]} · {d.title}")
        view.system_notice("tip: /kb list · /kb show <idx> · /kb search <query>")

    async def _kb_sync(_args: list[str]) -> None:
        """Push every document from the on-disk FileKnowledgeBase into the
        currently-active Pgvector KB.

        Use case: user accumulated content via /save while logged out
        (local KB), then logged in and wants those facts to live in the
        shared Postgres-backed retriever too. Source documents stay on
        disk — this is a copy, not a move, so a failed pg insert never
        loses the local copy.
        """
        from core.knowledge import FileKnowledgeBase, PgvectorKnowledgeBase
        from core.knowledge.local import DEFAULT_KB_ROOT

        cs = _csvc()
        if cs is None:
            view.error("kb", "feature unavailable")
            return
        kb_target = cs.service.knowledge
        if not isinstance(kb_target, PgvectorKnowledgeBase):
            view.error(
                "kb",
                "sync target is not pgvector — log in first (/login) so the "
                "active KB switches from local to pgvector.",
            )
            return

        # Read the on-disk source independently from whatever KB is wired
        # to ChatService. We need the LLM to embed; reuse the chat LLM
        # since it already has the embed model configured.
        src = FileKnowledgeBase.from_settings(llm=cs.service.llm)
        if src.root != DEFAULT_KB_ROOT and not src.root.exists():
            view.error("kb", f"local source not found at {src.root}")
            return
        try:
            local_docs = await src.list_documents()
        except Exception as exc:
            view.error("kb", f"read local: {type(exc).__name__}: {exc}")
            return
        if not local_docs:
            view.system_notice(f"local kb empty at {src.root} — nothing to sync")
            return

        view.system_notice(
            f"sync · {len(local_docs)} local doc(s) → pgvector · "
            "this re-embeds each chunk, may take a while"
        )
        ok = 0
        failed = 0
        for d in local_docs:
            got = await src.get_document(d.id)
            if got is None:
                failed += 1
                continue
            info, chunks = got
            # Rejoin chunks. Overlap was applied at original ingest time;
            # the target ingestor will split + embed afresh, so we feed
            # the rejoined content rather than the chunk-as-is to avoid
            # double-overlap artifacts.
            content = "\n\n".join(c for _, c in chunks)
            try:
                new_info = await kb_target.add_document(
                    title=info.title,
                    content=content,
                    source=f"sync-from-local:{info.id[:8]}",
                    tags=[*info.tags, "from-local"],
                )
            except Exception as exc:
                view.error("kb", f"  ✗ {info.title}: {type(exc).__name__}: {exc}")
                failed += 1
                continue
            view.system_notice(
                f"  ✓ {info.title[:50]} → {new_info.id[:8]} · "
                f"{new_info.chunk_count} chunk(s)"
            )
            ok += 1
        view.system_notice(
            f"sync done · {ok}/{len(local_docs)} OK"
            + (f" · {failed} failed" if failed else "")
        )

    _kb_subs: dict[str, Any] = {
        "list": _kb_list,
        "ls": _kb_list,
        "show": _kb_show,
        "search": _kb_search,
        "find": _kb_search,
        "delete": _kb_delete,
        "rm": _kb_delete,
        "sync": _kb_sync,
    }

    async def _kb(args: list[str]) -> None:
        if not args:
            await _kb_summary()
            return
        sub = args[0].lower()
        handler = _kb_subs.get(sub)
        if handler is None:
            view.error(
                "kb",
                f"unknown subcommand {sub!r} · try: list / show / search / delete",
            )
            return
        await handler(args[1:])

    # ------------------------------------------------------------------
    # /save — persist the last Q+A turn into the active KB
    #
    # ``last_turn`` is declared up-top with the other REPL state so the
    # session-resume path can seed it from replayed history. /save writes
    # "fact cards" the user explicitly endorses. Works against either KB
    # impl — FileKnowledgeBase (logged-out) or PgvectorKnowledgeBase
    # (logged-in) — since both expose the same ``add_document`` surface.
    # ------------------------------------------------------------------

    async def _save(args: list[str]) -> None:
        if not last_turn["user"] or not last_turn["assistant"]:
            view.error("save", "no completed turn yet — ask something first")
            return
        kb_active = await _kb_admin()
        if kb_active is None:
            return

        # Title: ``/save my title`` → "my title"; otherwise the leading
        # snippet of the user prompt (capped at 60 cells) so list output
        # stays one-line readable.
        title = " ".join(args).strip()
        if not title:
            head = last_turn["user"].splitlines()[0] if last_turn["user"] else ""
            title = head[:60] + ("…" if len(head) > 60 else "")
        content = (
            f"Q: {last_turn['user']}\n\n"
            f"A: {last_turn['assistant']}"
        )
        try:
            info = await kb_active.add_document(
                title=title or "(untitled)",
                content=content,
                source="repl-save",
                tags=["saved"],
            )
        except Exception as exc:
            view.error("save", f"{type(exc).__name__}: {exc}")
            return
        view.system_notice(
            f"saved → {_kb_label(kb_active)} · {info.id[:8]} · {info.title} · "
            f"{info.chunk_count} chunk(s) · /kb show {info.id[:8]}"
        )

    # ------------------------------------------------------------------
    # /reflect — auto-save high-quality turns
    #
    # When ``on``, after each successful assistant turn we run a small
    # critic LLM call to judge whether the Q+A is worth caching to the
    # local KB. ``save=true && confidence >= threshold`` → persist.
    #
    # Default off so first-time users don't see surprise side-effects.
    # ------------------------------------------------------------------
    reflect_state: dict[str, Any] = {"on": False, "threshold": 0.7, "critic": None}

    def _reflect(args: list[str]) -> None:
        if not args:
            on = bool(reflect_state["on"])
            thr = float(reflect_state["threshold"])
            view.system_notice(
                f"reflect {'on' if on else 'off'} · threshold {thr:.2f}"
            )
            return
        first = args[0].lower()
        if first in {"on", "off"}:
            new = first == "on"
            reflect_state["on"] = new
            view.system_notice(
                f"reflect {'on' if new else 'off'} · threshold "
                f"{float(reflect_state['threshold']):.2f}"
            )
            return
        # Numeric → set threshold (keeps reflect's on/off state untouched).
        try:
            val = float(first)
        except ValueError:
            view.error("reflect", "usage: /reflect [on|off|<0..1>]")
            return
        if not 0.0 <= val <= 1.0:
            view.error("reflect", f"threshold must be in [0,1], got {val}")
            return
        reflect_state["threshold"] = val
        view.system_notice(f"reflect threshold = {val:.2f}")

    async def _maybe_auto_save(user_text: str, asst_text: str) -> None:
        """Run the critic on a freshly-completed turn; persist if it clears
        the threshold. Silently no-ops when reflect is off, no KB is
        wired, or the critic returns no verdict. Works against both KB
        impls — auto-saves land in pgvector for logged-in users and in
        the local file KB otherwise."""
        if not reflect_state["on"]:
            return
        if not user_text.strip() or not asst_text.strip():
            return
        from core.knowledge import ReflectionCritic

        cs = _csvc()
        if cs is None:
            return
        # Cast to Any because the read-only ``KnowledgeBase`` Protocol
        # only exposes ``search``; both concrete impls (FileKB, Pgvector)
        # additionally expose the admin surface used below. Adding the
        # admin methods to the Protocol would force every future
        # retriever (read-only / search-only) to stub them out — that
        # asymmetry isn't worth a Protocol entry, so we narrow locally.
        from typing import Any as _Any
        from typing import cast as _cast

        kb_active = _cast(_Any, cs.service.knowledge)
        if kb_active is None:
            return

        critic = reflect_state.get("critic")
        if critic is None:
            critic = ReflectionCritic(llm=cs.service.llm)
            reflect_state["critic"] = critic

        try:
            verdict = await critic.judge(user_text, asst_text)
        except Exception as exc:
            view.error("reflect", f"{type(exc).__name__}: {exc}")
            return
        if verdict is None:
            return
        if not verdict.save:
            return
        if verdict.confidence < float(reflect_state["threshold"]):
            view.system_notice(
                f"reflect: skipped (confidence {verdict.confidence:.2f} < "
                f"threshold {float(reflect_state['threshold']):.2f})"
            )
            return
        # Persist. We prefer the critic's summary over the raw Q+A because
        # the critic distills it for retrieval — but include the original
        # question as a header so /kb show is still self-explanatory.
        content = (
            f"Q: {user_text.strip()}\n\n"
            f"Summary: {verdict.summary.strip()}\n\n"
            f"A: {asst_text.strip()}"
        )
        try:
            info = await kb_active.add_document(
                title=verdict.title or user_text[:60],
                content=content,
                source="repl-reflect",
                tags=[*verdict.tags, "auto-saved"],
            )
        except Exception as exc:
            view.error("reflect", f"persist failed: {type(exc).__name__}: {exc}")
            return
        view.system_notice(
            f"reflect saved → {_kb_label(kb_active)} · {info.id[:8]} · "
            f"{info.title} · confidence {verdict.confidence:.2f}"
        )

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
    dispatcher.register("kb", _kb)
    dispatcher.register("save", _save)
    dispatcher.register("reflect", _reflect)
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
            # Capture for /save and the auto-reflect critic. Empty ``full``
            # (Ctrl-C mid-stream, error) leaves last_turn at its prior
            # value — /save then complains "no completed turn yet" rather
            # than persisting a half-baked answer.
            if full:
                last_turn["user"] = line
                last_turn["assistant"] = full
                # Auto-reflect runs after the user-facing answer so it can
                # never block streaming. Errors are surfaced as a sys
                # notice rather than aborting the REPL loop.
                await _maybe_auto_save(line, full)

        view.system_notice("bye")
        return 0
    finally:
        if owned_provider:
            await provider.aclose()

