"""Per-user LLM rate-limiting facade.

Wraps :class:`service.platform.redis.RedisRateLimiter` with project-wide
defaults (read from ``settings.redis``) and exposes a single function the
HTTP/WS routes call before kicking off generation. Sharing one limiter
instance keeps the namespace + window stable across all entry points.

When Redis is disabled the call is a cheap no-op — production deploys
must enable Redis to actually enforce.
"""

from __future__ import annotations

from service.platform.redis import RedisRateLimiter

__all__ = ["enforce_user_llm_quota"]


_limiter: RedisRateLimiter | None = None


def _get_limiter() -> RedisRateLimiter:
    """Lazy build so we read settings *after* env loading is done."""
    global _limiter  # noqa: PLW0603 - module-level singleton
    if _limiter is None:
        from settings import settings

        _limiter = RedisRateLimiter(
            namespace="llm",
            limit=settings.redis.llm_rate_per_user,
            window_s=settings.redis.llm_rate_window_s,
        )
    return _limiter


async def enforce_user_llm_quota(*, user_id: str, provider: str = "default") -> None:
    """Charge one LLM call against the user's per-window budget.

    Raises :class:`service.llm.client.LLMRateLimitError` when the budget
    is exhausted; the exception carries ``retry_after`` (seconds) so the
    streaming layer surfaces it as ``Retry-After`` to the client.
    """
    limiter = _get_limiter()
    await limiter.enforce_llm(user_id=user_id, provider=provider)
