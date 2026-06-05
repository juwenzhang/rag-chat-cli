"""Process-wide Redis client + cache / rate-limit helpers.

Single connection pool per process, lazily created on first use. When
``settings.redis.enabled`` is ``False`` the helpers degrade to safe
no-ops (cache miss / rate-limit allow) so the backend stays bootable
without a Redis daemon during local dev.

Public surface:

* :func:`get_redis_client` — async client singleton.
* :func:`aclose_redis_client` — release the singleton (FastAPI lifespan).
* :func:`cached` — decorator caching JSON-serializable async returns.
* :class:`RedisRateLimiter` — fixed-window per-key limiter.
* :exc:`RedisDisabledError` — raised when callers force-require Redis.

Implementation choices:

* Fixed-window counter (``INCR`` + ``EXPIRE`` on first hit). Trades
  burst-edge accuracy for ~1ms simplicity; sliding-log can be added
  later behind the same :class:`RedisRateLimiter` API.
* Cache uses ``SET ... EX ttl``; deletion happens via Redis expiry, no
  manual eviction code path to maintain.
* All writes are best-effort: a Redis outage logs a warning and falls
  through to the wrapped function. We never fail a user request just
  because the cache is down.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar, cast

from service.llm.client import LLMRateLimitError

if TYPE_CHECKING:
    from redis.asyncio import Redis

__all__ = [
    "RedisDisabledError",
    "RedisRateLimiter",
    "aclose_redis_client",
    "cached",
    "get_redis_client",
]

logger = logging.getLogger(__name__)


class RedisDisabledError(RuntimeError):
    """Raised when Redis is required but ``settings.redis.enabled`` is False."""


# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------

_client: Redis | None = None
_lock = asyncio.Lock()


async def get_redis_client(*, required: bool = False) -> Redis | None:
    """Return the process-wide async Redis client.

    Returns ``None`` when ``settings.redis.enabled=False`` so callers can
    short-circuit gracefully. Pass ``required=True`` to force a
    :exc:`RedisDisabledError` instead — useful for paths that genuinely
    cannot work without Redis (e.g. job queues).
    """
    from settings import settings

    if not settings.redis.enabled:
        if required:
            raise RedisDisabledError(
                "Redis is disabled; set REDIS_ENABLED=true to enable this feature."
            )
        return None

    global _client
    if _client is not None:
        return _client

    async with _lock:
        if _client is None:
            from redis.asyncio import Redis as _Redis

            _client = _Redis.from_url(settings.redis.redis_url, decode_responses=True)
            logger.info("redis: connected to %s", _mask_url(settings.redis.redis_url))
    return _client


async def aclose_redis_client() -> None:
    """Release the singleton if it exists. Idempotent."""
    global _client
    if _client is None:
        return
    try:
        await _client.aclose()
    except (RuntimeError, OSError) as exc:  # pragma: no cover - defensive
        logger.warning("redis: aclose failed: %s", exc)
    _client = None


def _mask_url(url: str) -> str:
    """Hide credentials when logging the connection target."""
    if "@" not in url:
        return url
    head, tail = url.split("@", 1)
    if "://" in head:
        scheme, _ = head.split("://", 1)
        return f"{scheme}://***@{tail}"
    return f"***@{tail}"


# ---------------------------------------------------------------------------
# Cache decorator
# ---------------------------------------------------------------------------

T = TypeVar("T")
AsyncFunc = Callable[..., Awaitable[T]]


def cached(
    *,
    namespace: str,
    ttl: int | None = None,
    key_fn: Callable[..., str] | None = None,
) -> Callable[[AsyncFunc[T]], AsyncFunc[T]]:
    """Cache an async function's JSON-serializable return value.

    ``namespace`` is prepended to every key so collisions across modules
    are impossible. ``key_fn`` receives the same ``*args, **kwargs`` as
    the wrapped function and must return a stable string; default is a
    SHA1 of the repr — works for primitives, fragile for complex objects.

    A cache miss / Redis outage / decode error all fall through to the
    real function: the goal is "speed up the happy path", not "block on
    Redis". Set ``required=True`` upstream if you need hard reliance.
    """

    def deco(fn: AsyncFunc[T]) -> AsyncFunc[T]:
        @functools.wraps(fn)
        async def wrapped(*args: Any, **kwargs: Any) -> T:
            client = await get_redis_client()
            if client is None:
                return await fn(*args, **kwargs)

            from settings import settings

            effective_ttl = ttl if ttl is not None else settings.redis.cache_default_ttl
            key_part = key_fn(*args, **kwargs) if key_fn else _default_key(args, kwargs)
            full_key = f"cache:{namespace}:{key_part}"

            try:
                raw = await client.get(full_key)
            except (OSError, RuntimeError) as exc:
                logger.warning("redis: cache GET failed (%s): %s", full_key, exc)
                return await fn(*args, **kwargs)

            if raw is not None:
                try:
                    return cast("T", json.loads(raw))
                except json.JSONDecodeError as exc:
                    logger.warning("redis: cache decode failed (%s): %s", full_key, exc)

            value = await fn(*args, **kwargs)
            try:
                await client.set(full_key, json.dumps(value, default=str), ex=effective_ttl)
            except (OSError, TypeError, RuntimeError) as exc:
                logger.warning("redis: cache SET failed (%s): %s", full_key, exc)
            return value

        return wrapped

    return deco


def _default_key(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """SHA1-hashed stable key from positional + keyword args."""
    payload = repr((args, sorted(kwargs.items())))
    return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


class RedisRateLimiter:
    """Fixed-window counter limiter, scoped to ``namespace:key``.

    First hit in a window does ``INCR`` + ``EXPIRE`` so cleanup is free.
    When Redis is disabled the limiter always allows — production
    deployments **must** set ``REDIS_ENABLED=true`` to actually enforce.
    """

    def __init__(self, *, namespace: str, limit: int, window_s: int) -> None:
        if limit <= 0 or window_s <= 0:
            raise ValueError(f"limit/window must be positive, got {limit}/{window_s}")
        self._namespace: str = namespace
        self._limit: int = limit
        self._window_s: int = window_s

    async def hit(self, key: str) -> tuple[bool, int]:
        """Record one hit; return ``(allowed, retry_after_seconds)``.

        ``retry_after_seconds`` is 0 when allowed and the remaining TTL
        of the current window when blocked. Callers should surface that
        as ``Retry-After`` in HTTP / SSE error frames.
        """
        client = await get_redis_client()
        if client is None:
            return True, 0

        full_key = f"rl:{self._namespace}:{key}"
        try:
            count = int(await client.incr(full_key))
            if count == 1:
                await client.expire(full_key, self._window_s)
            if count > self._limit:
                ttl = int(await client.ttl(full_key))
                return False, max(ttl, 1)
            return True, 0
        except (OSError, RuntimeError) as exc:
            # Fail-open: a Redis blip should not 429 every user.
            logger.warning("redis: rate-limit hit failed (%s): %s", full_key, exc)
            return True, 0

    async def enforce_llm(self, *, user_id: str, provider: str) -> None:
        """Hit the limiter for an LLM call; raise on block.

        The raised exception carries ``code=LLMError.code`` matching
        ``FlowErrorCode.RATE_LIMITED`` so the streaming layer reports it
        identically to upstream-imposed 429s.
        """
        allowed, retry_after = await self.hit(f"{provider}:{user_id}")
        if allowed:
            return
        raise LLMRateLimitError(
            f"LLM call budget exceeded ({self._limit}/{self._window_s}s).",
            retry_after=retry_after,
        )
