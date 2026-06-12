"""Asset upload routes."""

from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.deps import get_current_user, get_db_session, get_session_factory
from api.schemas.asset import AssetOut
from service.db.models import Asset, User
from service.knowledge import KnowledgeService
from service.llm.ollama import OllamaClient
from service.platform.storage import ObjectStorage, build_object_storage
from service.platform.storage.images import normalize_image_to_webp
from service.platform.storage.uploads import UploadSession, UploadSessionStore
from service.platform.storage.vision import describe_image_asset
from service.providers.runtime import build_llm_for_user

__all__ = ["router"]

router = APIRouter(tags=["assets"])
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from service.llm.client import LLMClient
    from settings import Settings

_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
_WEBP_MAX_DIMENSION = 2048
_WEBP_QUALITY = 82
_DEFAULT_CHUNK_SIZE = 1 * 1024 * 1024  # 1 MiB
_MAX_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB
_UPLOAD_TMP_SUBDIR = "tmp/uploads"


class UploadCreateBody(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    content_type: str
    total_size: int = Field(ge=1, le=_MAX_IMAGE_BYTES)
    source_hash: str | None = Field(default=None, max_length=128)
    chunk_size: int | None = Field(default=None, ge=64 * 1024, le=_MAX_CHUNK_SIZE)


class UploadCreateOut(BaseModel):
    """Either an in-progress session or an immediate dedupe hit."""

    status: str  # "ready" | "completed"
    upload_id: str | None = None
    chunk_size: int | None = None
    expected_chunks: int | None = None
    received_chunks: list[int] | None = None
    asset: AssetOut | None = None


class UploadCompleteOut(BaseModel):
    status: str  # "completed"
    asset: AssetOut


@router.post("/assets/images", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> AssetOut:
    """Single-shot image upload (kept for small files / backwards compat)."""

    content_type = file.content_type or "application/octet-stream"
    _ensure_supported_image_type(content_type)
    data = await file.read()
    _ensure_image_bytes(data)

    asset, was_existing = await _persist_image_asset(
        request=request,
        session=session,
        session_factory=session_factory,
        user=user,
        data=data,
        filename=file.filename or "image",
        content_type=content_type,
    )
    if was_existing:
        response.status_code = status.HTTP_200_OK
    return await _to_out(asset, request)


# ----------------------------------------------------------- chunked upload


@router.post(
    "/assets/uploads",
    response_model=UploadCreateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_upload_session(
    body: UploadCreateBody,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UploadCreateOut:
    """Open a resumable chunked upload session.

    If the client provides ``source_hash`` we try to short-circuit the
    upload entirely: a hit on the user's existing assets returns the
    asset without ever transferring the bytes.
    """

    _ensure_supported_image_type(body.content_type)
    if body.total_size > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="image too large")

    if body.source_hash:
        existing = await _find_existing_image_by_source_hash(
            session,
            user_id=user.id,
            source_hash=body.source_hash,
        )
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return UploadCreateOut(status="completed", asset=await _to_out(existing, request))

    chunk_size = body.chunk_size or _DEFAULT_CHUNK_SIZE
    store = _upload_store(request)
    session_obj = await store.create(
        user_id=user.id,
        filename=body.filename,
        content_type=body.content_type,
        total_size=body.total_size,
        chunk_size=chunk_size,
        source_hash=body.source_hash,
    )
    return UploadCreateOut(
        status="ready",
        upload_id=session_obj.upload_id,
        chunk_size=session_obj.chunk_size,
        expected_chunks=session_obj.expected_chunks,
        received_chunks=[],
    )


@router.put(
    "/assets/uploads/{upload_id}/chunks/{index}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def put_upload_chunk(
    upload_id: str,
    index: int,
    request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    """Upload a single chunk's raw bytes for an open session."""

    store = _upload_store(request)
    session_obj = await _load_session(store, user_id=user.id, upload_id=upload_id)

    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="empty chunk")
    try:
        await store.write_chunk(session_obj, index=index, data=data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/assets/uploads/{upload_id}/complete",
    response_model=UploadCompleteOut,
)
async def complete_upload_session(
    upload_id: str,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> UploadCompleteOut:
    """Reassemble all chunks and run the standard image persistence pipeline."""

    store = _upload_store(request)
    session_obj = await _load_session(store, user_id=user.id, upload_id=upload_id)

    received = await store.received_indices(session_obj)
    if len(received) != session_obj.expected_chunks or received != list(
        range(session_obj.expected_chunks)
    ):
        raise HTTPException(
            status_code=400,
            detail=f"missing chunks: got {len(received)}/{session_obj.expected_chunks}",
        )

    try:
        data = await store.assemble(session_obj)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        asset, was_existing = await _persist_image_asset(
            request=request,
            session=session,
            session_factory=session_factory,
            user=user,
            data=data,
            filename=session_obj.filename,
            content_type=session_obj.content_type,
            source_hash_override=session_obj.source_hash,
        )
    finally:
        await store.discard(session_obj)

    if was_existing:
        response.status_code = status.HTTP_200_OK
    return UploadCompleteOut(status="completed", asset=await _to_out(asset, request))


@router.delete(
    "/assets/uploads/{upload_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_upload_session(
    upload_id: str,
    request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    """Discard an in-progress session and reclaim its scratch space."""

    store = _upload_store(request)
    try:
        session_obj = await _load_session(store, user_id=user.id, upload_id=upload_id)
    except HTTPException:
        # Idempotent: missing == already gone.
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    await store.discard(session_obj)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------- read route


@router.get("/assets/{asset_id}", response_model=AssetOut)
async def get_asset(
    asset_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AssetOut:
    row = await session.get(Asset, asset_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="asset not found")
    return await _to_out(row, request)


def _ensure_supported_image_type(content_type: str) -> None:
    if content_type not in _IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="only png/jpeg/webp/gif images are supported",
        )


def _ensure_image_bytes(data: bytes) -> None:
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="image too large")


def _upload_store(request: Request) -> UploadSessionStore:
    """Build (and cache on app.state) the chunked-upload temp store."""

    store = getattr(request.app.state, "upload_store", None)
    if isinstance(store, UploadSessionStore):
        return store
    settings = request.app.state.settings
    root = Path(settings.storage.local_root) / _UPLOAD_TMP_SUBDIR
    store = UploadSessionStore(root)
    request.app.state.upload_store = store
    return store


async def _load_session(
    store: UploadSessionStore,
    *,
    user_id: uuid.UUID,
    upload_id: str,
) -> UploadSession:
    try:
        return await store.get(user_id=user_id, upload_id=upload_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="upload session not found") from exc


async def _persist_image_asset(
    *,
    request: Request,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    user: User,
    data: bytes,
    filename: str,
    content_type: str,
    source_hash_override: str | None = None,
) -> tuple[Asset, bool]:
    """Run the shared dedupe + normalize + store + index pipeline.

    Returns ``(asset, was_existing)`` so the caller can decide whether
    to flip the response status from 201 to 200.
    """

    _ensure_image_bytes(data)
    source_hash = source_hash_override or _sha256_hex(data)

    # Trust-but-verify: clients can supply the hash so we can dedupe
    # before transferring bytes; if they lie we fall back to truth.
    if source_hash_override and source_hash != _sha256_hex(data):
        source_hash = _sha256_hex(data)

    existing = await _find_existing_image_by_source_hash(
        session,
        user_id=user.id,
        source_hash=source_hash,
    )
    if existing is not None:
        return existing, True

    try:
        normalized = await normalize_image_to_webp(
            data=data,
            filename=filename,
            content_type=content_type,
            max_dimension=_WEBP_MAX_DIMENSION,
            quality=_WEBP_QUALITY,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    storage = build_object_storage(request.app.state.settings)
    content_hash = _sha256_hex(normalized.data)
    existing = await _find_existing_image_by_content_hash(
        session,
        user_id=user.id,
        content_hash=content_hash,
    )
    if existing is None:
        existing = await _find_legacy_image_by_content_hash(
            session,
            storage,
            user_id=user.id,
            content_hash=content_hash,
            size_bytes=len(normalized.data),
        )
    if existing is not None:
        await _remember_source_hash(session, existing, source_hash)
        return existing, True

    asset_id = uuid.uuid4()
    key = f"assets/{user.id}/{content_hash}.webp"
    stored = await storage.put_bytes(
        key=key,
        data=normalized.data,
        content_type=normalized.content_type,
    )

    row = Asset(
        id=asset_id,
        user_id=user.id,
        filename=normalized.filename,
        content_type=normalized.content_type,
        size_bytes=len(normalized.data),
        storage_path=stored.key,
        source_hash=source_hash,
        content_hash=content_hash,
        description=normalized.description,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await _find_existing_image_by_source_hash(
            session,
            user_id=user.id,
            source_hash=source_hash,
        )
        if existing is None:
            existing = await _find_existing_image_by_content_hash(
                session,
                user_id=user.id,
                content_hash=content_hash,
            )
        if existing is None:
            raise
        return existing, True
    await session.refresh(row)
    await _try_index_image_asset(request, user, row, session, session_factory)
    return row, False


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _find_existing_image_by_source_hash(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    source_hash: str,
) -> Asset | None:
    return cast(
        Asset | None,
        await session.scalar(
            select(Asset)
            .where(Asset.user_id == user_id, Asset.source_hash == source_hash)
            .order_by(Asset.created_at.desc())
            .limit(1)
        ),
    )


async def _find_existing_image_by_content_hash(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    content_hash: str,
) -> Asset | None:
    return cast(
        Asset | None,
        await session.scalar(
            select(Asset)
            .where(Asset.user_id == user_id, Asset.content_hash == content_hash)
            .order_by(Asset.created_at.desc())
            .limit(1)
        ),
    )


async def _find_legacy_image_by_content_hash(
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    user_id: uuid.UUID,
    content_hash: str,
    size_bytes: int,
) -> Asset | None:
    rows = (
        await session.scalars(
            select(Asset)
            .where(
                Asset.user_id == user_id,
                Asset.content_hash.is_(None),
                Asset.content_type == "image/webp",
                Asset.size_bytes == size_bytes,
            )
            .order_by(Asset.created_at.desc())
        )
    ).all()
    for row in rows:
        try:
            existing_data = await storage.get_bytes(row.storage_path)
        except Exception as exc:
            logger.warning(
                "legacy image asset hash check failed asset_id=%s user_id=%s: %s",
                row.id,
                user_id,
                exc,
            )
            continue
        if _sha256_hex(existing_data) == content_hash:
            row.content_hash = content_hash
            return row
    return None


async def _remember_source_hash(
    session: AsyncSession,
    row: Asset,
    source_hash: str,
) -> None:
    if row.source_hash is not None:
        return
    row.source_hash = source_hash
    await session.commit()
    await session.refresh(row)


async def _try_index_image_asset(
    request: Request,
    user: User,
    row: Asset,
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = request.app.state.settings
    if not settings.retrieval.enabled:
        return
    storage = build_object_storage(settings)
    service = KnowledgeService(session, user_id=user.id)
    try:
        llm, _default_model = await build_llm_for_user(session_factory, user.id)
        try:
            caption = await _describe_image_with_vision_fallback(
                asset=row,
                storage=storage,
                user_llm=llm,
                settings=settings,
            )
            if caption:
                row.description = caption
                await session.commit()
                await session.refresh(row)
            body = _image_asset_index_body(row)
            doc = await service.create_document(
                source=f"asset://{row.id}",
                title=f"Image: {row.filename}",
                body=body,
                meta={"asset_id": str(row.id), "source_type": "image"},
            )
            await service.index_document(
                doc,
                session_factory=session_factory,
                llm=llm,
                settings=settings,
            )
        finally:
            await llm.aclose()
    except Exception as exc:
        logger.warning(
            "image asset auto-index failed asset_id=%s user_id=%s: %s", row.id, user.id, exc
        )


async def _describe_image_with_vision_fallback(
    *,
    asset: Asset,
    storage: ObjectStorage,
    user_llm: LLMClient,
    settings: Settings,
) -> str | None:
    if not settings.retrieval.image_caption_enabled:
        return None

    if settings.retrieval.image_caption_model:
        vision_llm = OllamaClient.from_settings(settings)
        try:
            caption = await describe_image_asset(
                asset=asset,
                storage=storage,
                llm=vision_llm,
                settings=settings,
            )
        finally:
            await vision_llm.aclose()
        if caption:
            return caption

    return await describe_image_asset(
        asset=asset,
        storage=storage,
        llm=user_llm,
        settings=settings,
    )


def _image_asset_index_body(row: Asset) -> str:
    return "\n".join(
        [
            f"![{row.filename}](asset://{row.id})",
            "",
            f"Filename: {row.filename}",
            f"Content type: {row.content_type}",
            f"Size: {row.size_bytes} bytes",
            f"Storage path: {row.storage_path}",
            row.description or "Image description is not available yet.",
        ]
    )


async def _to_out(row: Asset, request: Request) -> AssetOut:
    storage = build_object_storage(request.app.state.settings)
    return AssetOut(
        id=row.id,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        url=await storage.presigned_get_url(row.storage_path),
        description=row.description,
        created_at=row.created_at,
    )
