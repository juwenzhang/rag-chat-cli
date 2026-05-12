"""Background job queue + worker (#23 P5.4).

Public surface:

* :class:`JobSpec` — the unit of work (JSON-serializable).
* :class:`RedisJobQueue` — LPUSH / BRPOP over a Redis list.
* :class:`Worker` — pulls from a queue and dispatches by ``kind`` to a
  handler.
* :data:`JobHandler` — type alias for the handler signature.

Wiring example (CLI long-running ingest)::

    from core.workers import RedisJobQueue, Worker, JobSpec

    # producer side (e.g. ``main ingest --async``):
    queue = RedisJobQueue.from_url()
    await queue.enqueue(JobSpec(kind="ingest_document", payload={"path": "/x.md"}))
    await queue.aclose()

    # consumer side (``main worker``):
    queue = RedisJobQueue.from_url()
    worker = Worker(queue=queue)
    async def _handle(job): ...
    worker.register("ingest_document", _handle)
    await worker.run_forever()
"""

from __future__ import annotations

from core.workers.queue import DEFAULT_QUEUE_NAME, JobSpec, RedisJobQueue
from core.workers.worker import JobHandler, Worker

__all__ = [
    "DEFAULT_QUEUE_NAME",
    "JobHandler",
    "JobSpec",
    "RedisJobQueue",
    "Worker",
]
