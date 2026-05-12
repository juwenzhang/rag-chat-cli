"""Per-user LLM provider service — encryption + CRUD + remote IO.

Public surface used by ``api.routers.providers``:

* :class:`ProviderType` — string enum of supported provider kinds.
* :class:`ProviderInfo` — DTO carrying the *safe* projection of a row
  (no plaintext key; ``has_api_key`` boolean instead).
* :func:`encrypt_api_key` / :func:`decrypt_api_key` — Fernet wrappers
  driven by ``settings.security.provider_encryption_key``.
* :func:`list_providers` / :func:`get_provider` / :func:`create_provider`
  / :func:`update_provider` / :func:`delete_provider` — async CRUD.
* :func:`test_connectivity` — issue one HTTP call to the provider and
  return ``{"ok": bool, "detail": str}``. Used by ``POST /providers``
  and the ``/test`` endpoint.
* :func:`list_models` — call the provider's model-list endpoint
  (``/api/tags`` on Ollama, ``/v1/models`` on OpenAI-compatible) and
  normalize to ``[{"id": str, "size": int | None}]``.

Why a dedicated module: keeping the encryption surface narrow makes the
audit story easy — every read/write of ``providers.api_key_encrypted``
goes through this module. The API layer never touches Fernet directly.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Provider

logger = logging.getLogger(__name__)

__all__ = [
    "ProviderInfo",
    "ProviderNotFoundError",
    "ProviderType",
    "ProviderValidationError",
    "create_provider",
    "decrypt_api_key",
    "delete_provider",
    "encrypt_api_key",
    "get_provider",
    "list_models",
    "list_providers",
    "seed_default_ollama_for_user",
    "test_connectivity",
    "update_provider",
]


ProviderType = Literal["ollama", "openai"]
_SUPPORTED_TYPES: frozenset[str] = frozenset({"ollama", "openai"})

# Dev fallback only — surfaced with a warning when the real key is
# missing in env=dev. NEVER use in production.
_DEV_INSECURE_FERNET_KEY = "ZGV2LXJhZy1jbGktZml4ZWQtZGV2LWtleS0zMmJ5dGU="

_HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ProviderValidationError(ValueError):
    """Raised when input data fails validation (unknown type, bad URL …)."""


class ProviderNotFoundError(LookupError):
    """Raised when a provider id does not exist or is not owned by the user."""


# ---------------------------------------------------------------------------
# DTO
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProviderInfo:
    """Safe projection of a :class:`db.models.Provider` row.

    Never carries the plaintext API key. ``has_api_key`` lets the UI
    decide whether to show a "stored" badge versus an "add a key" CTA.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    type: str
    base_url: str
    has_api_key: bool
    is_default: bool
    enabled: bool

    @classmethod
    def from_row(cls, row: Provider) -> ProviderInfo:
        return cls(
            id=row.id,
            user_id=row.user_id,
            name=row.name,
            type=row.type,
            base_url=row.base_url,
            has_api_key=bool(row.api_key_encrypted),
            is_default=row.is_default,
            enabled=row.enabled,
        )


# ---------------------------------------------------------------------------
# Fernet
# ---------------------------------------------------------------------------


def _fernet() -> Fernet:
    """Lazy-build the process-wide Fernet using the configured key."""
    from settings import settings

    key = settings.security.provider_encryption_key
    if not key:
        if settings.app.env == "prod":
            raise RuntimeError(
                "PROVIDER_ENCRYPTION_KEY is required when APP_ENV=prod"
            )
        logger.warning(
            "PROVIDER_ENCRYPTION_KEY unset — falling back to a known dev key. "
            "DO NOT deploy to production with this configuration."
        )
        key = _DEV_INSECURE_FERNET_KEY
    return Fernet(key.encode("ascii") if isinstance(key, str) else key)


def encrypt_api_key(plaintext: str) -> str:
    """Encrypt ``plaintext`` for at-rest storage in ``providers.api_key_encrypted``."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_api_key(ciphertext: str | None) -> str | None:
    """Inverse of :func:`encrypt_api_key`. Returns ``None`` for ``None`` input.

    A corrupted ciphertext (e.g. rotated key without re-encrypting) raises
    :class:`cryptography.fernet.InvalidToken`. Callers should treat this
    as a configuration error, not a user-facing condition.
    """
    if ciphertext is None:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.error("provider api_key decrypt failed — key rotated without re-encrypting?")
        raise


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_type(t: str) -> None:
    if t not in _SUPPORTED_TYPES:
        raise ProviderValidationError(
            f"unsupported provider type: {t!r}. Must be one of {sorted(_SUPPORTED_TYPES)}"
        )


def _validate_base_url(url: str) -> None:
    if not url.startswith(("http://", "https://")):
        raise ProviderValidationError("base_url must start with http:// or https://")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def list_providers(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[ProviderInfo]:
    """Return every provider owned by ``user_id``, default first then by name."""
    q = (
        select(Provider)
        .where(Provider.user_id == user_id)
        .order_by(Provider.is_default.desc(), Provider.name.asc())
    )
    rows = (await session.scalars(q)).all()
    return [ProviderInfo.from_row(r) for r in rows]


async def get_provider(
    session: AsyncSession, *, user_id: uuid.UUID, provider_id: uuid.UUID
) -> Provider:
    """Return the ORM row for ``provider_id`` if owned by ``user_id``.

    Raises :class:`ProviderNotFoundError` otherwise — 404 vs 403 distinction
    is intentional (AGENTS.md §6 enumeration guidance).
    """
    row = await session.get(Provider, provider_id)
    if row is None or row.user_id != user_id:
        raise ProviderNotFoundError(str(provider_id))
    return row


async def create_provider(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    type: str,
    base_url: str,
    api_key: str | None,
    is_default: bool = False,
) -> Provider:
    """Create a new provider row.

    Does **not** perform connectivity test by itself — call
    :func:`test_connectivity` first if you want to fail fast. The API
    layer does that.
    """
    _validate_type(type)
    _validate_base_url(base_url)
    name = name.strip()
    if not name:
        raise ProviderValidationError("name is required")

    if is_default:
        # Clear the previous default; only one default per user.
        prior = await session.scalars(
            select(Provider).where(
                Provider.user_id == user_id, Provider.is_default.is_(True)
            )
        )
        for p in prior:
            p.is_default = False

    row = Provider(
        user_id=user_id,
        name=name,
        type=type,
        base_url=base_url.rstrip("/"),
        api_key_encrypted=encrypt_api_key(api_key) if api_key else None,
        is_default=is_default,
        enabled=True,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_provider(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    provider_id: uuid.UUID,
    name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    clear_api_key: bool = False,
    is_default: bool | None = None,
    enabled: bool | None = None,
) -> Provider:
    """Patch one provider. Only non-``None`` fields are touched.

    Pass ``clear_api_key=True`` to wipe the stored key (e.g. when switching
    from a hosted endpoint to local Ollama). Mutually exclusive with
    passing a non-``None`` ``api_key``.
    """
    row = await get_provider(
        session, user_id=user_id, provider_id=provider_id
    )

    if name is not None:
        name = name.strip()
        if not name:
            raise ProviderValidationError("name cannot be empty")
        row.name = name
    if base_url is not None:
        _validate_base_url(base_url)
        row.base_url = base_url.rstrip("/")
    if clear_api_key:
        if api_key is not None:
            raise ProviderValidationError(
                "pass either api_key or clear_api_key, not both"
            )
        row.api_key_encrypted = None
    elif api_key is not None:
        row.api_key_encrypted = encrypt_api_key(api_key) if api_key else None
    if enabled is not None:
        row.enabled = enabled
    if is_default is True:
        prior = await session.scalars(
            select(Provider).where(
                Provider.user_id == user_id,
                Provider.is_default.is_(True),
                Provider.id != row.id,
            )
        )
        for p in prior:
            p.is_default = False
        row.is_default = True
    elif is_default is False:
        row.is_default = False

    await session.commit()
    await session.refresh(row)
    return row


async def delete_provider(
    session: AsyncSession, *, user_id: uuid.UUID, provider_id: uuid.UUID
) -> None:
    """Hard-delete one provider. FK ``SET NULL`` clears it from sessions/prefs."""
    row = await get_provider(
        session, user_id=user_id, provider_id=provider_id
    )
    await session.delete(row)
    await session.commit()


# ---------------------------------------------------------------------------
# Remote IO — connectivity + model listing
# ---------------------------------------------------------------------------


def _auth_headers(api_key: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def test_connectivity(
    *, type: str, base_url: str, api_key: str | None
) -> dict[str, Any]:
    """Issue one cheap GET to probe the endpoint. Never raises.

    Returns ``{"ok": True, "detail": "..."}`` on a 2xx response or
    ``{"ok": False, "detail": "<reason>"}`` otherwise. Used by the API
    to fail fast when the user enters a wrong URL / dead key.
    """
    _validate_type(type)
    _validate_base_url(base_url)
    path = "/api/tags" if type == "ollama" else "/v1/models"
    url = base_url.rstrip("/") + path
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get(url, headers=_auth_headers(api_key))
        if 200 <= r.status_code < 300:
            return {"ok": True, "detail": f"HTTP {r.status_code} from {path}"}
        return {
            "ok": False,
            "detail": f"HTTP {r.status_code} from {path}: {r.text[:200]}",
        }
    except httpx.HTTPError as exc:
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


async def list_models(
    *, type: str, base_url: str, api_key: str | None
) -> list[dict[str, Any]]:
    """Fetch the provider's model list and normalize.

    Returns ``[{"id": str, "size": int | None}]``. ``size`` is bytes for
    Ollama, ``None`` for OpenAI-compatible (the wire format doesn't
    expose it).

    Raises :class:`httpx.HTTPError` on transport failure and
    :class:`ProviderValidationError` on unsupported types — callers
    should map these to 502 / 400 respectively.
    """
    _validate_type(type)
    _validate_base_url(base_url)
    headers = _auth_headers(api_key)

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        if type == "ollama":
            r = await client.get(
                base_url.rstrip("/") + "/api/tags", headers=headers
            )
            r.raise_for_status()
            payload = r.json()
            return [
                {"id": m.get("name", ""), "size": m.get("size")}
                for m in payload.get("models", [])
                if m.get("name")
            ]
        # openai-compatible
        r = await client.get(
            base_url.rstrip("/") + "/v1/models", headers=headers
        )
        r.raise_for_status()
        payload = r.json()
        return [
            {"id": m.get("id", ""), "size": None}
            for m in payload.get("data", [])
            if m.get("id")
        ]


# ---------------------------------------------------------------------------
# Onboarding — seed a default Ollama provider on first use
# ---------------------------------------------------------------------------


async def seed_default_ollama_for_user(
    session: AsyncSession, *, user_id: uuid.UUID
) -> Provider | None:
    """Create a starter Ollama provider for ``user_id`` if they have none.

    Idempotent. Returns the newly-created row, or ``None`` when:

    * the user already has at least one :class:`db.models.Provider` row, or
    * the ``OLLAMA_BASE_URL`` setting is unset.

    Reads ``settings.ollama.base_url`` / ``api_key`` / ``chat_model`` so the
    seed mirrors the env config the operator already chose for the CLI.

    No connectivity probe — the goal is "make local Ollama visible
    without manual setup". If Ollama isn't running, the row still appears
    and the user can edit/delete it from the settings UI.

    NOTE: we deliberately do **not** gate on the existence of a
    :class:`db.models.UserPreference` row. ``GET /me/preferences`` lazily
    creates one with empty defaults, and gating on that would mean a
    single accidental preference read locks the user out of auto-seed
    forever. Re-seeding after explicit deletion is acceptable in V1.
    """
    from db.models import UserPreference

    existing = await session.scalar(
        select(Provider).where(Provider.user_id == user_id).limit(1)
    )
    if existing is not None:
        return None

    from settings import settings

    base_url = settings.ollama.base_url
    if not base_url:
        return None

    row = Provider(
        user_id=user_id,
        name="local-ollama",
        type="ollama",
        base_url=base_url.rstrip("/"),
        api_key_encrypted=(
            encrypt_api_key(settings.ollama.api_key)
            if settings.ollama.api_key
            else None
        ),
        is_default=True,
        enabled=True,
    )
    session.add(row)
    await session.flush()  # need row.id for the pref pointer

    # Upsert the user_preferences row so the new provider is also the
    # default. If a row already exists (e.g., GET /me/preferences ran
    # earlier and lazy-created it), just point its ``default_provider_id``
    # at the seeded entry — don't fail with PK conflict.
    pref_row = await session.get(UserPreference, user_id)
    if pref_row is None:
        pref_row = UserPreference(
            user_id=user_id,
            default_provider_id=row.id,
            default_model=settings.ollama.chat_model or None,
            default_use_rag=False,
        )
        session.add(pref_row)
    else:
        pref_row.default_provider_id = row.id
        if pref_row.default_model is None:
            pref_row.default_model = settings.ollama.chat_model or None

    await session.commit()
    await session.refresh(row)
    logger.info(
        "seeded default Ollama provider for user %s -> %s", user_id, base_url
    )
    return row
