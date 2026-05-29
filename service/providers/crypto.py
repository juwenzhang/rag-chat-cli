"""Provider API-key encryption helpers."""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

__all__ = ["decrypt_api_key", "encrypt_api_key"]

logger = logging.getLogger(__name__)

_DEV_INSECURE_FERNET_KEY = "ZGV2LXJhZy1jbGktZml4ZWQtZGV2LWtleS0zMmJ5dGU="


def _fernet() -> Fernet:
    """Lazy-build the process-wide Fernet using the configured key."""
    from settings import settings

    key = settings.security.provider_encryption_key
    if not key:
        if settings.app.env == "prod":
            raise RuntimeError("PROVIDER_ENCRYPTION_KEY is required when APP_ENV=prod")
        logger.warning(
            "PROVIDER_ENCRYPTION_KEY unset — falling back to a known dev key. "
            "DO NOT deploy to production with this configuration."
        )
        key = _DEV_INSECURE_FERNET_KEY
    return Fernet(key.encode("ascii") if isinstance(key, str) else key)


def encrypt_api_key(plaintext: str) -> str:
    """Encrypt ``plaintext`` for at-rest storage."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_api_key(ciphertext: str | None) -> str | None:
    """Decrypt an at-rest provider API key."""
    if ciphertext is None:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.error("provider api_key decrypt failed — key rotated without re-encrypting?")
        raise
