"""Service-layer domain errors.

These exceptions deliberately avoid HTTP concerns. Entry layers translate them
to transport-specific errors such as FastAPI ``HTTPException``.
"""

from __future__ import annotations

__all__ = ["ForbiddenError", "NotFoundError"]


class NotFoundError(LookupError):
    """Requested domain resource is missing or intentionally hidden."""


class ForbiddenError(PermissionError):
    """Caller is known but lacks the required permission."""
