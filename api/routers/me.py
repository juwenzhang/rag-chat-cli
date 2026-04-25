"""``/me`` routes — current user read + limited patch."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db_session
from api.schemas.auth import UserOut
from api.schemas.me import UserPatchIn
from db.models import User

__all__ = ["router"]

router = APIRouter(tags=["me"])


@router.get(
    "/me",
    response_model=UserOut,
    summary="Return the authenticated user",
)
async def get_me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.patch(
    "/me",
    response_model=UserOut,
    summary="Patch the authenticated user (whitelisted fields)",
)
async def patch_me(
    body: UserPatchIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserOut:
    # Only ``display_name`` is patchable today; schema enforces the whitelist.
    if body.display_name is not None:
        user.display_name = body.display_name
    await session.merge(user)
    await session.commit()
    return UserOut.model_validate(user)
