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

import json
import uuid
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.deps import get_current_user, get_db_session
from api.schemas.common import OkResponse
from api.schemas.provider import (
    ConnectivityTestIn,
    ConnectivityTestOut,
    ModelListItem,
    ModelMetaIn,
    ProviderCreateIn,
    ProviderOut,
    ProviderUpdateIn,
    PullModelIn,
    UserPreferenceIn,
    UserPreferenceOut,
)
from core.providers import (
    ProviderInfo,
    ProviderNotFoundError,
    ProviderValidationError,
    create_provider,
    decrypt_api_key,
    delete_ollama_model,
    delete_provider,
    get_provider,
    list_model_meta_for_provider,
    list_models,
    list_providers,
    pull_ollama_model,
    running_ollama_models,
    seed_default_ollama_for_user,
    show_ollama_model,
    test_connectivity,
    update_provider,
    upsert_model_meta,
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
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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

    # Join with model_metadata so the UI can render hover descriptions in
    # one round-trip instead of a second per-model fetch.
    descriptions = await list_model_meta_for_provider(
        session, provider_id=provider_id
    )
    return [
        ModelListItem(
            id=m["id"],
            size=m.get("size"),
            kind=m.get("kind", "chat"),
            description=descriptions.get(m["id"]),
        )
        for m in items
    ]


@router.post(
    "/providers/{provider_id}/models/meta",
    response_model=OkResponse,
    summary="Attach (or clear) a user description for one model",
)
async def upsert_model_meta_route(
    provider_id: uuid.UUID,
    body: ModelMetaIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OkResponse:
    try:
        # Ownership check — `upsert_model_meta` itself only takes provider_id.
        await get_provider(
            session, user_id=user.id, provider_id=provider_id
        )
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="provider not found") from exc

    await upsert_model_meta(
        session,
        provider_id=provider_id,
        model=body.model,
        description=body.description,
    )
    return OkResponse(ok=True)


# ---------------------------------------------------------------------------
# Providers — pull an Ollama model (streaming progress)
# ---------------------------------------------------------------------------


@router.post(
    "/providers/{provider_id}/models/pull",
    summary="Pull an Ollama model — streams progress as SSE",
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": (
                "Server-Sent Events stream. Each frame is `event: progress` "
                "carrying Ollama's raw NDJSON progress dict, terminated by "
                "`event: done` on success or `event: error` on failure."
            ),
        },
    },
)
async def pull_model_route(
    provider_id: uuid.UUID,
    body: PullModelIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    try:
        row = await get_provider(
            session, user_id=user.id, provider_id=provider_id
        )
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="provider not found") from exc

    if row.type != "ollama":
        raise HTTPException(
            status_code=400,
            detail="model pull is only supported for Ollama providers",
        )

    api_key = decrypt_api_key(row.api_key_encrypted)
    model_tag = body.model.strip()
    if not model_tag:
        raise HTTPException(status_code=400, detail="model tag is required")

    sse_headers = {
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }

    async def _byte_stream() -> AsyncIterator[bytes]:
        saw_error = False
        async for chunk in pull_ollama_model(
            base_url=row.base_url, api_key=api_key, model=model_tag
        ):
            if "error" in chunk:
                saw_error = True
                yield _sse_frame(
                    "error",
                    {"code": "OLLAMA_PULL", "message": str(chunk["error"])},
                )
                return
            yield _sse_frame("progress", chunk)
            # Ollama emits ``status: success`` as the terminal frame; convert
            # that to our own done event so the UI has a uniform end signal.
            if str(chunk.get("status", "")).lower() == "success":
                yield _sse_frame("done", {"model": model_tag})
                return
        if not saw_error:
            # Stream ended without a status=success — emit done anyway so the
            # UI doesn't hang. The progress frames already gave context.
            yield _sse_frame("done", {"model": model_tag})

    return StreamingResponse(
        _byte_stream(), media_type="text/event-stream", headers=sse_headers
    )


def _sse_frame(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")


# ---------------------------------------------------------------------------
# Providers — Ollama model CRUD (delete / show / ps)
#
# Why these mirror Ollama's REST surface so closely: the platform is, as we
# tell users, "a runner for your own Ollama" (cf. Claude Code Desktop). So
# exposing pull / delete / show / ps directly keeps the management surface
# 1:1 with the underlying daemon — no proprietary abstractions to learn.
# ---------------------------------------------------------------------------


def _ollama_provider_or_400(row: Provider) -> None:
    if row.type != "ollama":
        raise HTTPException(
            status_code=400, detail="this operation is only valid for Ollama providers"
        )


@router.post(
    "/providers/{provider_id}/models/delete",
    response_model=OkResponse,
    summary="Delete a model from the Ollama daemon",
)
async def delete_provider_model_route(
    provider_id: uuid.UUID,
    body: PullModelIn,  # reused: same {"model": "..."} shape; tag may contain ":" and "/"
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OkResponse:
    """``POST`` (not ``DELETE``) so we can carry the model tag in a JSON body
    rather than the URL — Ollama tags can include ``/`` (namespaced models
    like ``library/qwen2.5:7b``) and ``:``, which makes path-based encoding
    fiddly across nginx / Next / fetch. The semantic is still "delete".
    """
    try:
        row = await get_provider(
            session, user_id=user.id, provider_id=provider_id
        )
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="provider not found") from exc
    _ollama_provider_or_400(row)

    api_key = decrypt_api_key(row.api_key_encrypted)
    try:
        await delete_ollama_model(
            base_url=row.base_url, api_key=api_key, model=body.model
        )
    except httpx.HTTPStatusError as exc:
        status_code = 404 if exc.response.status_code == 404 else 502
        raise HTTPException(
            status_code=status_code,
            detail=f"ollama: HTTP {exc.response.status_code}: {exc.response.text[:200]}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"provider upstream error: {type(exc).__name__}: {exc}",
        ) from exc
    return OkResponse(ok=True)


@router.post(
    "/providers/{provider_id}/models/show",
    summary="Show one model's details (license, params, modelfile) via Ollama /api/show",
)
async def show_provider_model_route(
    provider_id: uuid.UUID,
    body: PullModelIn,  # reused: same {"model": "..."} shape
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        row = await get_provider(
            session, user_id=user.id, provider_id=provider_id
        )
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="provider not found") from exc
    _ollama_provider_or_400(row)

    api_key = decrypt_api_key(row.api_key_encrypted)
    try:
        return await show_ollama_model(
            base_url=row.base_url, api_key=api_key, model=body.model
        )
    except httpx.HTTPStatusError as exc:
        status_code = 404 if exc.response.status_code == 404 else 502
        raise HTTPException(
            status_code=status_code,
            detail=f"ollama: HTTP {exc.response.status_code}: {exc.response.text[:200]}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"provider upstream error: {type(exc).__name__}: {exc}",
        ) from exc


@router.get(
    "/providers/{provider_id}/ps",
    summary="List currently-loaded models via Ollama /api/ps",
)
async def list_running_models_route(
    provider_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    try:
        row = await get_provider(
            session, user_id=user.id, provider_id=provider_id
        )
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="provider not found") from exc
    _ollama_provider_or_400(row)

    api_key = decrypt_api_key(row.api_key_encrypted)
    try:
        return await running_ollama_models(
            base_url=row.base_url, api_key=api_key
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"provider upstream error: {type(exc).__name__}: {exc}",
        ) from exc


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

    if body.clear_default_embedding_model:
        pref.default_embedding_model = None
    elif body.default_embedding_model is not None:
        pref.default_embedding_model = body.default_embedding_model

    if body.default_use_rag is not None:
        pref.default_use_rag = body.default_use_rag

    await session.commit()
    await session.refresh(pref)
    return UserPreferenceOut.model_validate(pref)
