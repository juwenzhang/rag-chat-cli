"""Bcrypt-backed password hashing (AGENTS.md §6, add-jwt-auth/design.md).

Thin wrapper around :mod:`passlib` so the rest of the codebase never touches
``CryptContext`` directly. The cost factor is driven by
``settings.auth.bcrypt_rounds``; callers pass ``plain`` strings, never bytes.

Compatibility shim: passlib 1.7.4 reads ``bcrypt.__about__.__version__`` at
backend-load time, but bcrypt 4.x dropped that attribute. The lookup is
guarded inside passlib so it only emits a noisy ``(trapped) error reading
bcrypt version`` log line — the hash itself works fine. We synthesize a fake
``__about__`` module before passlib touches bcrypt so the trap never fires.
"""

from __future__ import annotations

import logging
import sys
import types
from functools import lru_cache

# --- bcrypt 4.x compat: rebuild the legacy ``bcrypt.__about__`` namespace --
# Do this BEFORE passlib imports bcrypt. Cheap and idempotent.
try:
    import bcrypt as _bcrypt

    if not hasattr(_bcrypt, "__about__"):
        _about = types.ModuleType("bcrypt.__about__")
        _about.__version__ = getattr(_bcrypt, "__version__", "0.0.0")  # type: ignore[attr-defined]
        sys.modules["bcrypt.__about__"] = _about
        _bcrypt.__about__ = _about  # type: ignore[attr-defined]
except ImportError:
    # bcrypt not installed — passlib will surface the real error itself.
    pass

# Silence the "(trapped) error reading bcrypt version" line that passlib
# logs once at first use even when the fallback succeeds. We can't unwind
# the trap (it's deep in passlib internals) but we can mute its logger.
logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.ERROR)
logging.getLogger("passlib.utils.compat").setLevel(logging.ERROR)


from passlib.context import CryptContext  # noqa: E402  — must come AFTER the shim above

__all__ = ["hash_password", "verify_password"]


@lru_cache(maxsize=1)
def _context() -> CryptContext:
    """Build the :class:`CryptContext` lazily.

    Cached so test fixtures that mutate ``settings`` before the first call
    still see the right rounds; after that the instance is reused.
    """
    # Late import keeps ``core.auth`` free from the settings singleton until
    # the first actual hash operation.
    from settings import settings

    return CryptContext(
        schemes=["bcrypt"],
        deprecated="auto",
        bcrypt__rounds=settings.auth.bcrypt_rounds,
    )


def hash_password(plain: str) -> str:
    """Return the bcrypt hash for ``plain``. Constant-time verification via
    :func:`verify_password`."""
    return str(_context().hash(plain))


def verify_password(plain: str, hashed: str) -> bool:
    """Return True iff ``plain`` matches ``hashed``. Never raises on bad input."""
    try:
        return bool(_context().verify(plain, hashed))
    except ValueError:
        # Malformed hash in DB → treat as verification failure.
        return False
