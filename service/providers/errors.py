"""Provider service exceptions."""

from __future__ import annotations

__all__ = ["ProviderNotFoundError", "ProviderValidationError"]


class ProviderValidationError(ValueError):
    """Raised when input data fails validation."""


class ProviderNotFoundError(LookupError):
    """Raised when a provider id does not exist or is not owned by the user."""
