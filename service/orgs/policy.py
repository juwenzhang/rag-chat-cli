"""Organization membership and authorization policy."""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from service.db.models import OrgMember
from service.errors import ForbiddenError, NotFoundError

__all__ = ["get_membership", "require_role"]

_ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}


async def get_membership(
    session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
) -> OrgMember | None:
    """Return the membership row or ``None`` if the user is not in the org."""
    return cast(
        OrgMember | None,
        await session.scalar(
            select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == user_id)
        ),
    )


async def require_role(
    session: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    min_role: str,
) -> OrgMember:
    """Return membership if caller has at least ``min_role``.

    Raises service-layer errors instead of HTTP exceptions so this policy can
    be reused by REST, WebSocket, CLI, and workers.
    """
    member = await get_membership(session, org_id, user_id)
    if member is None:
        raise NotFoundError("org not found")
    if _ROLE_RANK[member.role] < _ROLE_RANK[min_role]:
        raise ForbiddenError(f"requires {min_role} role")
    return member
