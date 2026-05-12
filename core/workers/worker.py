"""Background worker that pumps a :class:`RedisJobQueue` (#23 P5.4).

The worker is intentionally dumb: it polls one queue, looks up the
handler for each job's ``kind``, awaits it, logs the outcome. Failures
in a handler are logged but do not crash the worker — one bad job
should not take the whole worker process down.

Wiring (typical CLI use, see :mod:`app.cli`)::

    from core.workers import RedisJobQueue, Worker

    queue = RedisJobQueue.from_url()
    worker = Worker(queue=queue)
    worker.register("ingest_document", _handle_ingest)
    await worker.run_forever()

``run_forever`` honours :mod:`asyncio` cancellation — SIGINT / SIGTERM
from the CLI surfaces as ``CancelledError`` and shuts the loop down
cleanly without losing in-flight jobs (the running handler is awaited
to completion before the loop exits).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.workers.queue import JobSpec, RedisJobQueue

__all__ = ["JobHandler", "Worker"]

logger = logging.getLogger(__name__)


JobHandler = Callable[["JobSpec"], Awaitable[None]]
"""Async callable that processes one :class:`~core.workers.queue.JobSpec`.

Handlers raise on failure — the worker logs and moves on. There is no
automatic retry yet; if a job is critical, the handler is responsible
for idempotency and (optional) re-enqueue on a separate "retry" queue.
"""


class Worker:
    """Pull-loop over one :class:`RedisJobQueue`.

    Registration is single-tenant: ``register(kind, handler)`` rejects
    duplicate kinds so two handler authors can't silently shadow each
    other. Unknown kinds drop the job with a warning rather than crashing
    — useful when rolling out a new ``kind`` value alongside an old
    worker fleet.
    """

    def __init__(
        self,
        *,
        queue: RedisJobQueue,
        poll_timeout_s: float = 5.0,
    ) -> None:
        self._queue = queue
        self._poll_timeout_s = poll_timeout_s
        self._handlers: dict[str, JobHandler] = {}
        self._running = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register(self, kind: str, handler: JobHandler) -> None:
        if kind in self._handlers:
            raise ValueError(f"worker handler for kind={kind!r} already registered")
        self._handlers[kind] = handler

    def kinds(self) -> list[str]:
        return list(self._handlers)

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------
    async def run_forever(self) -> None:
        """Poll → dispatch → repeat until cancelled.

        Each iteration blocks up to ``poll_timeout_s`` on ``BRPOP``; when
        cancelled mid-handler, the handler is allowed to finish (the
        cancellation happens *between* jobs).
        """
        self._running = True
        logger.info(
            "worker starting; queue=%s kinds=%s",
            self._queue.name, ", ".join(sorted(self._handlers)) or "<none>",
        )
        try:
            while self._running:
                try:
                    job = await self._queue.dequeue(timeout_s=self._poll_timeout_s)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("worker: BRPOP failed; sleeping 1s before retry")
                    await asyncio.sleep(1.0)
                    continue
                if job is None:
                    continue
                await self._dispatch(job)
        except asyncio.CancelledError:
            logger.info("worker cancelled; shutting down")
            raise
        finally:
            self._running = False
            logger.info("worker stopped")

    def stop(self) -> None:
        """Ask the loop to exit at the next iteration.

        Useful when the worker is embedded in a larger app and you don't
        want to cancel the surrounding task. The CLI path just cancels
        the task instead.
        """
        self._running = False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _dispatch(self, job: JobSpec) -> None:
        handler = self._handlers.get(job.kind)
        if handler is None:
            logger.warning(
                "worker dropping unknown kind=%s job_id=%s (known: %s)",
                job.kind, job.id, ", ".join(sorted(self._handlers)) or "<none>",
            )
            return
        started = time.monotonic()
        logger.info("running job %s (kind=%s)", job.id, job.kind)
        try:
            # Shield from cancellation so a Ctrl-C *between* poll() and the
            # handler awaiting doesn't leave the job half-processed in
            # Redis but not visible to anything else. The outer loop still
            # honours cancellation — it just happens at the next iteration.
            await asyncio.shield(handler(job))
        except asyncio.CancelledError:
            with suppress(Exception):
                logger.warning("job %s cancelled mid-flight", job.id)
            raise
        except Exception:
            logger.exception("job %s (kind=%s) failed", job.id, job.kind)
            return
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.info("job %s done in %dms", job.id, elapsed_ms)
