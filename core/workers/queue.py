"""Redis-list-backed async job queue (#23 P5.4).

Single queue per name, FIFO order via ``LPUSH`` + ``BRPOP``. Job bodies are
JSON-encoded ``JobSpec`` dataclasses. No retry / DLQ / scheduling in this
first pass — that's what Celery/RQ exist for; this module is the cheap
``< 200 LOC`` baseline for "ingest a 5MB doc without blocking the CLI".

Why not Redis Streams (XADD/XREADGROUP)?
  Streams give consumer groups + delivery guarantees. We don't need either
  yet — workers are single-tenant CLI background processes, and "lost job
  on crash" is acceptable for ingestion (re-run the CLI command).

If/when those guarantees matter, swap the body of :meth:`RedisJobQueue.enqueue`
and :meth:`RedisJobQueue.dequeue` to use ``XADD`` / ``XREADGROUP`` —
``JobSpec`` and :class:`~core.workers.worker.Worker` stay unchanged.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redis.asyncio import Redis

__all__ = [
    "DEFAULT_QUEUE_NAME",
    "JobSpec",
    "RedisJobQueue",
]

logger = logging.getLogger(__name__)


DEFAULT_QUEUE_NAME = "rag-ai-cli:jobs"


@dataclass(frozen=True, slots=True)
class JobSpec:
    """One unit of work enqueued for a worker.

    ``kind`` is a short routing tag — the worker uses it to look up the
    handler. ``payload`` carries arbitrary JSON-serializable arguments;
    keeping it loose avoids forcing a separate dataclass per job type.

    ``id`` is auto-generated so we can correlate enqueue / consume /
    completion events in logs without the caller having to thread a
    trace id through.
    """

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    enqueued_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> JobSpec:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError(f"JobSpec.from_json expected a JSON object, got {data!r}")
        kind = data.get("kind")
        if not isinstance(kind, str) or not kind:
            raise ValueError(f"JobSpec.from_json missing 'kind' field: {data!r}")
        raw_payload = data.get("payload")
        payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
        return cls(
            kind=kind,
            payload=payload,
            id=str(data.get("id") or uuid.uuid4().hex),
            enqueued_at=str(data.get("enqueued_at") or datetime.now(timezone.utc).isoformat()),
        )


class RedisJobQueue:
    """LPUSH / BRPOP FIFO queue over a Redis list.

    Construct with a ``redis.asyncio.Redis`` client (typically built from
    ``settings.redis.redis_url`` via :meth:`from_url`). The queue does NOT
    own the connection: callers wire one client across many queues and
    close it at shutdown.
    """

    def __init__(
        self,
        redis: Redis,
        *,
        name: str = DEFAULT_QUEUE_NAME,
    ) -> None:
        self._r = redis
        self._name = name

    @classmethod
    def from_url(
        cls,
        url: str | None = None,
        *,
        name: str = DEFAULT_QUEUE_NAME,
    ) -> RedisJobQueue:
        """Build directly from a Redis URL.

        ``None`` reads ``settings.redis.redis_url``. The returned queue owns
        the underlying client, so call :meth:`aclose` at shutdown.
        """
        from redis.asyncio import Redis as _Redis

        if url is None:
            from settings import settings

            url = settings.redis.redis_url
        client = _Redis.from_url(url, decode_responses=True)
        q = cls(client, name=name)
        q._owns_client = True  # type: ignore[attr-defined]
        return q

    @property
    def name(self) -> str:
        return self._name

    # ------------------------------------------------------------------
    # Enqueue / dequeue
    # ------------------------------------------------------------------
    async def enqueue(self, job: JobSpec) -> None:
        """Push a job to the head of the list — workers ``BRPOP`` from the
        tail, giving FIFO order.

        Failures bubble up as ``redis.exceptions.ConnectionError`` etc.;
        callers should decide whether to retry inline or surface the
        error to the user.
        """
        await self._r.lpush(self._name, job.to_json())  # type: ignore[misc]
        logger.info("enqueued job %s (kind=%s)", job.id, job.kind)

    async def dequeue(self, *, timeout_s: float = 5.0) -> JobSpec | None:
        """Block for up to ``timeout_s`` waiting for the next job.

        Returns ``None`` on timeout so the worker loop can poll a shutdown
        flag in between. ``timeout_s=0`` would block forever — disallowed
        for that reason.
        """
        if timeout_s <= 0:
            raise ValueError(f"timeout_s must be > 0, got {timeout_s}")
        # BRPOP returns ``(key, value)`` or ``None`` on timeout. The
        # ``redis`` package uses an int seconds parameter; we round up so
        # very-short configured timeouts still poll at least once.
        result = await self._r.brpop(self._name, timeout=max(1, int(timeout_s + 0.999)))  # type: ignore[misc]
        if result is None:
            return None
        _key, raw = result
        try:
            return JobSpec.from_json(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("dropping malformed job (%s): %r", exc, raw[:200])
            return None

    async def length(self) -> int:
        """Number of jobs currently queued. Useful for ops dashboards."""
        return int(await self._r.llen(self._name))  # type: ignore[misc]

    async def aclose(self) -> None:
        """Close the underlying Redis client if we own it (created via
        :meth:`from_url`). No-op otherwise — the caller manages lifecycle."""
        if getattr(self, "_owns_client", False):
            await self._r.aclose()
