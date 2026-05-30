"""Asset upload routes."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.deps import get_current_user, get_db_session, get_session_factory
from api.schemas.asset import AssetOut
from service.db.models import Asset, User
from service.knowledge import KnowledgeService
from service.providers.runtime import build_llm_for_user
from service.storage import build_object_storage
from service.storage.images import normalize_image_to_webp
from service.storage.vision import describe_image_asset

__all__ = ["router"]

router = APIRouter(tags=["assets"])
logger = logging.getLogger(__name__)

_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
_WEBP_MAX_DIMENSION = 2048
_WEBP_QUALITY = 82


@router.post("/assets/images", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> AssetOut:
    content_type = file.content_type or "application/octet-stream"
    if content_type not in _IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="only png/jpeg/webp/gif images are supported")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="image too large")

    try:
        normalized = await normalize_image_to_webp(
            data=data,
            filename=file.filename or "image",
            content_type=content_type,
            max_dimension=_WEBP_MAX_DIMENSION,
            quality=_WEBP_QUALITY,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    asset_id = uuid.uuid4()
    key = f"assets/{user.id}/{asset_id}.webp"
    storage = build_object_storage(request.app.state.settings)
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
        description=normalized.description,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    await _try_index_image_asset(request, user, row, session, session_factory)
    return await _to_out(row, request)


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
            caption = await describe_image_asset(
                asset=row,
                storage=storage,
                llm=llm,
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
