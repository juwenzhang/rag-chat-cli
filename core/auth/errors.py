"""Auth-layer exception hierarchy.

Every concrete error inherits from :class:`AuthError` so callers (CLI, future
FastAPI handler) can map them with a single ``isinstance`` check.

Design note: messages are deliberately generic. In particular
:class:`InvalidCredentialsError` must **not** disclose whether it was the
email or the password that was wrong — otherwise attackers can enumerate
accounts. See AGENTS.md §6 and ``openspec/changes/add-jwt-auth/design.md``.
"""

from __future__ import annotations

__all__ = [
    "AuthError",
    "EmailAlreadyExistsError",
    "InvalidCredentialsError",
    "TokenExpiredError",
    "TokenInvalidError",
    "TokenReuseError",
    "UserNotActiveError",
]


class AuthError(Exception):
    """Base class for every authentication / authorization error."""


class InvalidCredentialsError(AuthError):
    """Email unknown or password did not match. Message stays generic."""


class EmailAlreadyExistsError(AuthError):
    """An account with the supplied email already exists."""


class TokenExpiredError(AuthError):
    """Token signature is valid but the ``exp`` claim is in the past."""


class TokenInvalidError(AuthError):
    """Token could not be decoded, was tampered with, or has the wrong type."""


class TokenReuseError(AuthError):
    """A refresh token that had already been revoked was presented again.

    The :class:`AuthService` interprets this as a potential token theft and
    mass-revokes the user's remaining refresh tokens.
    """


class UserNotActiveError(AuthError):
    """Account exists but ``is_active`` is False."""
