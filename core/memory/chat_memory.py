"""Conversation memory — Protocol + two concrete implementations.

The Protocol exists so the REST / SSE / WS / CLI surfaces can all depend on
a single abstraction while we switch backends:

* :class:`FileChatMemory` — "1 session = 1 JSON file" under :pyattr:`root`.
  Kept as an offline fallback for CLI boot paths where no user is logged in
  (and for cheap local dev / tests without spinning up a DB).

* :class:`DbChatMemory` — persists into ``chat_sessions`` / ``messages``
  via SQLAlchemy async. This is the production backend used by every
  authenticated surface (REST ``POST /chat/messages``, SSE ``POST /chat/stream``,
  WS ``/ws/chat`` and the CLI once logged in).

``session_id`` is always a string at the Protocol boundary. ``DbChatMemory``
converts it to :class:`uuid.UUID` internally; ``FileChatMemory`` treats it as
an opaque token. This keeps :class:`core.chat_service.ChatService` agnostic
to the storage choice.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from core.llm.client import ChatMessage, ToolCall

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from core.llm.client import Role

__all__ = ["ChatMemory", "DbChatMemory", "FileChatMemory", "SessionMeta"]


# ---------------------------------------------------------------------------
# ChatMessage ↔ persistent dict (#7 P1.6 tool fields)
# ---------------------------------------------------------------------------


def _message_to_dict(msg: ChatMessage) -> dict[str, Any]:
    """Serialize a :class:`ChatMessage` to a JSON-safe dict.

    Only writes the tool-flavoured fields when they carry information so
    pre-#7 readers (and the FileChatMemory's on-disk format) stay
    backward-compatible: a plain user/assistant turn round-trips as
    ``{"role": ..., "content": ...}`` exactly like before.
    """
    out: dict[str, Any] = {"role": msg.role, "content": msg.content}
    if msg.tool_calls:
        out["tool_calls"] = [
            {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
            for tc in msg.tool_calls
        ]
    if msg.tool_call_id is not None:
        out["tool_call_id"] = msg.tool_call_id
    return out


def _parse_tool_calls(raw: Any) -> tuple[ToolCall, ...]:
    """Decode a raw JSON list into a tuple of :class:`ToolCall`.

    Used by both file and DB backends — kept here so the round-trip rules
    are defined once. Malformed entries are skipped silently because the
    upstream writer was *this* module; surfacing parse errors would block
    a user's session over a single bad row.
    """
    if not isinstance(raw, list) or not raw:
        return ()
    out: list[ToolCall] = []
    for tc in raw:
        if not isinstance(tc, dict):
            continue
        if "id" not in tc or "name" not in tc:
            continue
        args = tc.get("arguments")
        if not isinstance(args, dict):
            args = {}
        out.append(ToolCall(id=str(tc["id"]), name=str(tc["name"]), arguments=args))
    return tuple(out)


def _dict_to_message(item: dict[str, Any]) -> ChatMessage:
    """Inverse of :func:`_message_to_dict`. Tolerates missing tool fields."""
    tool_call_id = item.get("tool_call_id")
    return ChatMessage(
        role=cast("Role", item["role"]),
        content=item.get("content") or "",
        tool_calls=_parse_tool_calls(item.get("tool_calls")),
        tool_call_id=tool_call_id if isinstance(tool_call_id, str) else None,
    )


def _db_row_to_message(row: Any) -> ChatMessage:
    """Reconstruct a :class:`ChatMessage` from a :class:`db.models.Message` row.

    Kept separate from :func:`_dict_to_message` so the SQLAlchemy ORM types
    stay out of file-only code paths (importing :class:`db.models.Message`
    eagerly here would drag SQLAlchemy into ``FileChatMemory`` users).
    """
    tool_call_id = getattr(row, "tool_call_id", None)
    return ChatMessage(
        role=cast("Role", row.role),
        content=row.content,
        tool_calls=_parse_tool_calls(getattr(row, "tool_calls", None)),
        tool_call_id=tool_call_id if isinstance(tool_call_id, str) else None,
    )


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SessionMeta:
    """Display-side metadata for one chat session — what the sidebar shows.

    ``title`` is either the user-set DB title (DB backend) or a synthesized
    preview built from the first user message (file backend, or DB rows
    where ``title IS NULL``). ``message_count`` is informational only;
    ``updated_at`` is best-effort (file backend uses mtime).
    """

    id: str
    title: str
    message_count: int
    updated_at: datetime | None


def _synthesize_title(messages: list[ChatMessage], *, max_chars: int = 24) -> str:
    """Take the first user message and return its first ``max_chars`` chars.

    Used by both backends when no explicit title is stored. Returns
    ``"(empty)"`` when there is no user message yet so the sidebar never
    shows a blank row.
    """
    for msg in messages:
        if msg.role == "user" and msg.content.strip():
            text = msg.content.strip()
            if len(text) <= max_chars:
                return text
            return text[:max_chars] + "…"
    return "(empty)"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ChatMemory(Protocol):
    """Minimal async chat-memory contract.

    All methods are async so DB-backed and file-backed implementations share
    the exact same call sites. ``session_id`` is an opaque string token; the
    concrete backend decides how to interpret it.
    """

    async def new_session(self) -> str: ...
    async def list_sessions(self) -> list[str]: ...
    async def list_session_metas(self) -> list[SessionMeta]: ...
    async def get(self, session_id: str) -> list[ChatMessage]: ...
    async def append(self, session_id: str, msg: ChatMessage) -> None: ...
    async def delete_session(self, session_id: str) -> None: ...
    async def set_title(self, session_id: str, title: str) -> None: ...


# ---------------------------------------------------------------------------
# File backend (offline fallback, unchanged behaviour from pre-v1.2)
# ---------------------------------------------------------------------------


def _atomic_write(path: Path, payload: bytes) -> None:
    """Write ``payload`` to ``path`` atomically via a sibling ``.tmp`` file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)


class FileChatMemory:
    """One JSON file per session, under :pyattr:`root`.

    Used as the offline / unauthenticated fallback on the CLI boot path.
    """

    def __init__(self, root: str | os.PathLike[str] = "./conversations") -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    @classmethod
    def from_settings(cls, s: Any | None = None) -> FileChatMemory:
        # settings has no dedicated field yet; keep default path.
        del s  # unused — reserved for future MEMORY_DIR setting
        return cls()

    # ------------------------------------------------------------------
    @property
    def root(self) -> Path:
        return self._root

    def _path(self, session_id: str) -> Path:
        if not session_id or "/" in session_id or session_id.startswith("."):
            raise ValueError(f"invalid session id: {session_id!r}")
        return self._root / f"{session_id}.json"

    # ------------------------------------------------------------------
    async def new_session(self) -> str:
        session_id = secrets.token_hex(8)

        def _create() -> None:
            _atomic_write(self._path(session_id), b"[]")

        await asyncio.to_thread(_create)
        return session_id

    async def list_sessions(self) -> list[str]:
        def _scan() -> list[str]:
            return sorted(p.stem for p in self._root.glob("*.json"))

        return await asyncio.to_thread(_scan)

    async def get(self, session_id: str) -> list[ChatMessage]:
        path = self._path(session_id)

        def _read() -> list[ChatMessage]:
            if not path.exists():
                return []
            raw = json.loads(path.read_text(encoding="utf-8"))
            return [_dict_to_message(item) for item in raw]

        return await asyncio.to_thread(_read)

    async def append(self, session_id: str, msg: ChatMessage) -> None:
        path = self._path(session_id)

        def _mutate() -> None:
            existing: list[dict[str, Any]] = []
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
            existing.append(_message_to_dict(msg))
            _atomic_write(
                path,
                json.dumps(existing, ensure_ascii=False).encode("utf-8"),
            )

        await asyncio.to_thread(_mutate)

    async def delete_session(self, session_id: str) -> None:
        path = self._path(session_id)

        def _unlink() -> None:
            if path.exists():
                path.unlink()

        await asyncio.to_thread(_unlink)

    # ------------------------------------------------------------------
    # Sidebar / TUI helpers
    # ------------------------------------------------------------------
    async def list_session_metas(self) -> list[SessionMeta]:
        """Read every session file and synthesize a SessionMeta for each.

        The title is derived from the first user message (24-char preview)
        because file backend has no place to store an explicit title.
        Sorted by mtime descending so the most recently used session is
        always first.

        Empty sessions (no messages) are filtered out — they're typically
        leftover from CLI processes that started a session but exited
        before the user sent anything. Keeping them clutters the sidebar
        with ``(empty)`` rows that the user can't usefully act on.
        """

        def _scan() -> list[SessionMeta]:
            metas: list[SessionMeta] = []
            for path in self._root.glob("*.json"):
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(raw, list):
                    continue
                msgs = [
                    _dict_to_message(item)
                    for item in raw
                    if isinstance(item, dict) and "role" in item and "content" in item
                ]
                if not msgs:
                    continue  # skip empty sessions
                title = _synthesize_title(msgs)
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
                metas.append(
                    SessionMeta(
                        id=path.stem,
                        title=title,
                        message_count=len(msgs),
                        updated_at=mtime,
                    )
                )
            metas.sort(key=lambda m: m.updated_at or datetime.min, reverse=True)
            return metas

        return await asyncio.to_thread(_scan)

    async def set_title(self, session_id: str, title: str) -> None:
        """No-op: file backend doesn't store an explicit title.

        Method exists to satisfy the :class:`ChatMemory` Protocol; callers
        get a deliberate silent ignore so the TUI ``/title`` command degrades
        gracefully when the user is not logged in.
        """
        del session_id, title  # intentionally unused


# ---------------------------------------------------------------------------
# DB backend
# ---------------------------------------------------------------------------


class DbChatMemory:
    """Persist chat history into Postgres / SQLite via SQLAlchemy async.

    Every public method opens a short-lived :class:`AsyncSession` via the
    injected factory. We deliberately do *not* hold a long-lived session on
    the instance — the instance lives as long as a :class:`ChatService`
    (one per user request / one per CLI process), but each DB access should
    have its own transactional scope.

    Cross-user isolation is defence-in-depth: routes already check ownership,
    but :meth:`get` / :meth:`delete_session` also verify ``chat_sessions.user_id``
    matches the bound ``user_id`` so a forged session_id can't read someone
    else's history.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        user_id: uuid.UUID,
    ) -> None:
        self._sf = session_factory
        self._user_id = user_id

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _as_uuid(session_id: str) -> uuid.UUID:
        try:
            return uuid.UUID(session_id)
        except ValueError as exc:
            # Match FileChatMemory's failure shape so call sites see a
            # uniform ValueError regardless of backend.
            raise ValueError(f"invalid session id: {session_id!r}") from exc

    # ------------------------------------------------------------------
    # ChatMemory Protocol
    # ------------------------------------------------------------------
    async def new_session(self) -> str:
        # Imports live inside methods to keep core/memory import-light (so
        # tests that only touch FileChatMemory don't drag in SQLAlchemy).
        from db.models import ChatSession

        async with self._sf() as s:
            row = ChatSession(user_id=self._user_id, title=None)
            s.add(row)
            await s.commit()
            return str(row.id)

    async def list_sessions(self) -> list[str]:
        from sqlalchemy import select

        from db.models import ChatSession

        async with self._sf() as s:
            q = (
                select(ChatSession.id)
                .where(ChatSession.user_id == self._user_id)
                .order_by(ChatSession.updated_at.desc())
            )
            rows = (await s.scalars(q)).all()
            return [str(r) for r in rows]

    async def get(self, session_id: str) -> list[ChatMessage]:
        from sqlalchemy import select

        from db.models import ChatSession, Message

        sid = self._as_uuid(session_id)
        async with self._sf() as s:
            # Defence-in-depth ownership check — return [] rather than raise
            # so a stale session_id (e.g. after /logout) degrades gracefully.
            owner = await s.scalar(select(ChatSession.user_id).where(ChatSession.id == sid))
            if owner is None or owner != self._user_id:
                return []
            q = select(Message).where(Message.session_id == sid).order_by(Message.created_at.asc())
            rows = (await s.scalars(q)).all()
            # ``Message.role`` is a string column; ChatMessage.role is a
            # Literal union. Cast here: the DB is trusted to only hold values
            # produced by the service layer (user / assistant / system / tool).
            return [_db_row_to_message(r) for r in rows]

    async def append(self, session_id: str, msg: ChatMessage) -> None:
        from db.models import Message

        sid = self._as_uuid(session_id)
        async with self._sf() as s:
            s.add(
                Message(
                    session_id=sid,
                    role=msg.role,
                    content=msg.content,
                    tool_call_id=msg.tool_call_id,
                    tool_calls=(
                        [
                            {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                            for tc in msg.tool_calls
                        ]
                        if msg.tool_calls
                        else None
                    ),
                )
            )
            await s.commit()

    async def delete_session(self, session_id: str) -> None:
        from db.models import ChatSession

        sid = self._as_uuid(session_id)
        async with self._sf() as s:
            row = await s.get(ChatSession, sid)
            if row is None or row.user_id != self._user_id:
                return
            await s.delete(row)  # FK cascade removes messages
            await s.commit()

    # ------------------------------------------------------------------
    # Sidebar / TUI helpers
    # ------------------------------------------------------------------
    async def list_session_metas(self) -> list[SessionMeta]:
        """Return one :class:`SessionMeta` per session owned by ``user_id``.

        ``title`` is ``COALESCE(chat_sessions.title, <preview>)``. The
        preview is computed by issuing one extra SELECT per session for the
        first user message — N+1 but typical users have < 50 sessions and
        this only runs on TUI sidebar refresh, not on hot paths.
        """
        from sqlalchemy import select

        from db.models import ChatSession, Message

        async with self._sf() as s:
            sess_q = (
                select(ChatSession)
                .where(ChatSession.user_id == self._user_id)
                .order_by(ChatSession.updated_at.desc())
            )
            rows = (await s.scalars(sess_q)).all()

            metas: list[SessionMeta] = []
            for row in rows:
                count_q = (
                    select(Message)
                    .where(Message.session_id == row.id)
                    .order_by(Message.created_at.asc())
                )
                msgs = (await s.scalars(count_q)).all()
                count = len(msgs)
                if count == 0:
                    continue  # hide empty sessions from the sidebar
                if row.title:
                    title = row.title
                else:
                    chat_msgs = [_db_row_to_message(m) for m in msgs]
                    title = _synthesize_title(chat_msgs)
                metas.append(
                    SessionMeta(
                        id=str(row.id),
                        title=title,
                        message_count=count,
                        updated_at=row.updated_at,
                    )
                )
            return metas

    async def set_title(self, session_id: str, title: str) -> None:
        """``UPDATE chat_sessions SET title=? WHERE id=? AND user_id=?``.

        Silently no-ops when the session is not owned by ``self._user_id``
        — same defence-in-depth pattern as :meth:`get`.
        """
        from db.models import ChatSession

        sid = self._as_uuid(session_id)
        async with self._sf() as s:
            row = await s.get(ChatSession, sid)
            if row is None or row.user_id != self._user_id:
                return
            row.title = title
            await s.commit()
