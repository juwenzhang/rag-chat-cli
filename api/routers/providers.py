"""``/providers`` + ``/me/preferences`` routes (Sprint 2).

Endpoints
---------

* ``GET    /providers``                      — list user's providers
* ``POST   /providers``                      — create (optionally fail fast on connectivity)
* ``PATCH  /providers/{id}``                 — partial update
* ``DELETE /providers/{id}``                 — hard delete
* ``GET    /providers/{id}/models``          — live model list from upstream
* ``POST   /providers/test``                 — anonymous probe (used by the Add form)

* ``GET    /me/preferences``                 — return current per-user defaults
* ``PUT    /me/preferences``                 — upsert per-user defaults

Models are listed live (no DB cache) — the cost is one cheap HTTP GET. A
short in-memory TTL cache is fine to add later if it becomes hot; for now
it would obscure the "is this provider currently reachable" signal.
"""

from __future__ import annotations

import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db_session
from api.schemas.common import OkResponse
from api.schemas.provider import (
    ConnectivityTestIn,
    ConnectivityTestOut,
    ModelListItem,
    ProviderCreateIn,
    ProviderOut,
    ProviderUpdateIn,
    UserPreferenceIn,
    UserPreferenceOut,
)
from core.providers import (
    ProviderInfo,
    ProviderNotFoundError,
    ProviderValidationError,
    create_provider,
    decrypt_api_key,
    delete_provider,
    get_provider,
    list_models,
    list_providers,
    seed_default_ollama_for_user,
    test_connectivity,
    update_provider,
)
from db.models import Provider, User, UserPreference

__all__ = ["router"]

router = APIRouter(tags=["providers"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _info_to_out(info: ProviderInfo) -> ProviderOut:
    return ProviderOut(
        id=info.id,
        name=info.name,
        type=info.type,
        base_url=info.base_url,
        has_api_key=info.has_api_key,
        is_default=info.is_default,
        enabled=info.enabled,
    )


def _row_to_out(row: Provider) -> ProviderOut:
    return _info_to_out(ProviderInfo.from_row(row))


def _validation_400(exc: ProviderValidationError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Providers — CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/providers",
    response_model=list[ProviderOut],
    summary="List the current user's LLM providers",
)
async def list_providers_route(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ProviderOut]:
    items = await list_providers(session, user_id=user.id)
    if not items:
        # First-time user — try to seed a starter Ollama provider from env.
        # Returns ``None`` if the user has already been through onboarding
        # (a UserPreference row exists), so deletes are not auto-revived.
        seeded = await seed_default_ollama_for_user(session, user_id=user.id)
        if seeded is not None:
            items = await list_providers(session, user_id=user.id)
    return [_info_to_out(p) for p in items]


@router.post(
    "/providers",
    response_model=ProviderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new LLM provider",
)
async def create_provider_route(
    body: ProviderCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProviderOut:
    base_url = str(body.base_url).rstrip("/")
    if body.test_connectivity:
        result = await test_connectivity(
            type=body.type, base_url=base_url, api_key=body.api_key
        )
        if not result["ok"]:
            raise HTTPException(
                status_code=400,
                detail=f"connectivity test failed: {result['detail']}",
            )
    try:
        row = await create_provider(
            session,
            user_id=user.id,
            name=body.name,
            type=body.type,
            base_url=base_url,
            api_key=body.api_key,
            is_default=body.is_default,
        )
    except ProviderValidationError as exc:
        raise _validation_400(exc) from exc
    return _row_to_out(row)


@router.patch(
    "/providers/{provider_id}",
    response_model=ProviderOut,
    summary="Patch one provider",
)
async def update_provider_route(
    provider_id: uuid.UUID,
    body: ProviderUpdateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProviderOut:
    try:
        row = await update_provider(
            session,
            user_id=user.id,
            provider_id=provider_id,
            name=body.name,
            base_url=str(body.base_url).rstrip("/") if body.base_url else None,
            api_key=body.api_key,
            clear_api_key=body.clear_api_key,
            is_default=body.is_default,
            enabled=body.enabled,
        )
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="provider not found") from exc
    except ProviderValidationError as exc:
        raise _validation_400(exc) from exc
    return _row_to_out(row)


@router.delete(
    "/providers/{provider_id}",
    response_model=OkResponse,
    summary="Delete one provider",
)
async def delete_provider_route(
    provider_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OkResponse:
    try:
        await delete_provider(
            session, user_id=user.id, provider_id=provider_id
        )
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="provider not found") from exc
    return OkResponse(ok=True)


# ---------------------------------------------------------------------------
# Providers — model list (live)
# ---------------------------------------------------------------------------


@router.get(
    "/providers/{provider_id}/models",
    response_model=list[ModelListItem],
    summary="List models available on the upstream provider (live, uncached)",
)
async def list_models_route(
    provider_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ModelListItem]:
    try:
        row = await get_provider(
            session, user_id=user.id, provider_id=provider_id
        )
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="provider not found") from exc

    api_key = decrypt_api_key(row.api_key_encrypted)
    try:
        items = await list_models(
            type=row.type, base_url=row.base_url, api_key=api_key
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"provider upstream error: {type(exc).__name__}: {exc}",
        ) from exc
    except ProviderValidationError as exc:
        raise _validation_400(exc) from exc

    return [ModelListItem(id=m["id"], size=m.get("size")) for m in items]


# ---------------------------------------------------------------------------
# Providers — anonymous connectivity probe (used by "Add provider" form)
# ---------------------------------------------------------------------------


@router.post(
    "/providers/test",
    response_model=ConnectivityTestOut,
    summary="Probe a provider URL without persisting anything",
)
async def test_provider_route(
    body: ConnectivityTestIn,
    _: User = Depends(get_current_user),
) -> ConnectivityTestOut:
    result = await test_connectivity(
        type=body.type,
        base_url=str(body.base_url).rstrip("/"),
        api_key=body.api_key,
    )
    return ConnectivityTestOut(ok=bool(result["ok"]), detail=str(result["detail"]))


# ---------------------------------------------------------------------------
# User preferences
# ---------------------------------------------------------------------------


async def _get_or_create_pref(
    session: AsyncSession, user_id: uuid.UUID
) -> UserPreference:
    """Return the user's preferences row, creating an empty one on miss.

    Seeding is *not* done here — that belongs to ``GET /providers`` so
    parallel client calls (the chat model selector fetches both endpoints
    at once) don't race on inserting into the same PK.
    """
    pref = await session.get(UserPreference, user_id)
    if pref is not None:
        return pref
    pref = UserPreference(user_id=user_id, default_use_rag=False)
    session.add(pref)
    await session.commit()
    await session.refresh(pref)
    return pref


@router.get(
    "/me/preferences",
    response_model=UserPreferenceOut,
    summary="Return per-user default provider/model/RAG",
)
async def get_preferences_route(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserPreferenceOut:
    pref = await _get_or_create_pref(session, user.id)
    return UserPreferenceOut.model_validate(pref)


@router.put(
    "/me/preferences",
    response_model=UserPreferenceOut,
    summary="Upsert per-user default provider/model/RAG",
)
async def put_preferences_route(
    body: UserPreferenceIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserPreferenceOut:
    pref = await _get_or_create_pref(session, user.id)

    if body.clear_default_provider:
        pref.default_provider_id = None
    elif body.default_provider_id is not None:
        # Defence in depth: the provider must be owned by ``user``.
        try:
            await get_provider(
                session, user_id=user.id, provider_id=body.default_provider_id
            )
        except ProviderNotFoundError as exc:
            raise HTTPException(
                status_code=400, detail="default_provider_id does not exist"
            ) from exc
        pref.default_provider_id = body.default_provider_id

    if body.clear_default_model:
        pref.default_model = None
    elif body.default_model is not None:
        pref.default_model = body.default_model

    if body.default_use_rag is not None:
        pref.default_use_rag = body.default_use_rag

    await session.commit()
    await session.refresh(pref)
    return UserPreferenceOut.model_validate(pref)
