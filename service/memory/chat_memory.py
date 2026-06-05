"""Conversation memory — Protocol + DB-backed implementation.

The Protocol exists so REST / SSE / WS / TUI surfaces all depend on the
same abstraction; today the only concrete backend is :class:`DbChatMemory`,
which persists into ``chat_sessions`` / ``messages`` via SQLAlchemy async.
Pre-server CLI fallback (file-backed JSON per session) was removed — the
TUI now always talks to the server, so the offline path is gone.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from service.chat.titles import synthesize_preview_title
from service.llm.client import ChatMessage, ToolCall

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from service.llm.client import Role

__all__ = ["ChatMemory", "DbChatMemory", "SessionMeta"]


# ---------------------------------------------------------------------------
# ChatMessage ↔ persistent dict (#7 P1.6 tool fields)
# ---------------------------------------------------------------------------


def _parse_tool_calls(raw: Any) -> tuple[ToolCall, ...]:
    """Decode a raw JSON list of tool-call dicts into typed :class:`ToolCall` s.

    Malformed entries are skipped silently because the upstream writer is
    this module — surfacing per-row parse errors would block a session
    over a single bad row.
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


def _db_row_to_message(row: Any) -> ChatMessage:
    """Reconstruct a :class:`ChatMessage` from a :class:`db.models.Message` row."""
    tool_call_id = getattr(row, "tool_call_id", None)
    raw_sources = getattr(row, "sources", None)
    return ChatMessage(
        role=cast("Role", row.role),
        content=row.content,
        tool_calls=_parse_tool_calls(getattr(row, "tool_calls", None)),
        tool_call_id=tool_call_id if isinstance(tool_call_id, str) else None,
        tool_name="tool" if getattr(row, "role", None) == "tool" else None,
        sources=(
            tuple(s for s in raw_sources if isinstance(s, dict))
            if isinstance(raw_sources, list)
            else ()
        ),
    )


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SessionMeta:
    """Display-side metadata for one chat session — what the sidebar shows.

    ``title`` is the user-set DB title, or a preview synthesized from the
    first user message when ``chat_sessions.title IS NULL``.
    """

    id: str
    title: str
    message_count: int
    updated_at: datetime | None


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ChatMemory(Protocol):
    """Minimal async chat-memory contract — DB-backed in production."""

    async def new_session(self) -> str: ...
    async def list_sessions(self) -> list[str]: ...
    async def list_session_metas(self) -> list[SessionMeta]: ...
    async def get(self, session_id: str) -> list[ChatMessage]: ...
    async def append(self, session_id: str, msg: ChatMessage) -> None: ...
    async def delete_session(self, session_id: str) -> None: ...
    async def set_title(self, session_id: str, title: str) -> None: ...
    async def get_title(self, session_id: str) -> str | None: ...


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
            raise ValueError(f"invalid session id: {session_id!r}") from exc

    # ------------------------------------------------------------------
    # ChatMemory Protocol
    # ------------------------------------------------------------------
    async def new_session(self) -> str:
        from service.db.models import ChatSession

        async with self._sf() as s:
            row = ChatSession(user_id=self._user_id, title=None)
            s.add(row)
            await s.commit()
            return str(row.id)

    async def list_sessions(self) -> list[str]:
        from sqlalchemy import select

        from service.db.models import ChatSession

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

        from service.db.models import ChatSession, Message

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
        from service.db.models import Message

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
                    sources=list(msg.sources) if msg.sources else None,
                )
            )
            await s.commit()

    async def delete_session(self, session_id: str) -> None:
        from service.db.models import ChatSession

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

        from service.db.models import ChatSession, Message

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
                    title = synthesize_preview_title(chat_msgs)
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
        from service.db.models import ChatSession

        sid = self._as_uuid(session_id)
        async with self._sf() as s:
            row = await s.get(ChatSession, sid)
            if row is None or row.user_id != self._user_id:
                return
            row.title = title
            await s.commit()

    async def get_title(self, session_id: str) -> str | None:
        """Return the explicitly-stored title (or ``None``).

        Used by the auto-title hook in :class:`~service.chat.service.ChatService`
        to avoid clobbering a title a user already set via ``/title``.
        """
        from service.db.models import ChatSession

        sid = self._as_uuid(session_id)
        async with self._sf() as s:
            row = await s.get(ChatSession, sid)
            if row is None or row.user_id != self._user_id:
                return None
            return row.title
