"""Wiki authorization policy."""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from service.db.models import Org, Wiki, WikiMember
from service.errors import ForbiddenError, NotFoundError
from service.orgs.policy import get_membership as get_org_membership

__all__ = ["EffectiveRole", "require_wiki_role", "resolve_wiki_role"]

EffectiveRole = Literal["owner", "editor", "viewer"]
_RANK = {"viewer": 1, "editor": 2, "owner": 3}


async def resolve_wiki_role(
    session: AsyncSession, wiki: Wiki, user_id: uuid.UUID
) -> EffectiveRole | None:
    """Return caller's effective role in ``wiki`` or ``None`` if inaccessible."""
    org = await session.get(Org, wiki.org_id)
    if org is None:
        return None
    if org.owner_id == user_id:
        return "owner"

    org_member = await get_org_membership(session, wiki.org_id, user_id)
    if wiki.visibility == "private":
        wiki_member = await session.scalar(
            select(WikiMember).where(
                WikiMember.wiki_id == wiki.id,
                WikiMember.user_id == user_id,
            )
        )
        if wiki_member is None:
            return None
        return wiki_member.role  # type: ignore[return-value]

    if org_member is None:
        return None
    return org_member.role  # type: ignore[return-value]


async def require_wiki_role(
    session: AsyncSession,
    wiki: Wiki,
    user_id: uuid.UUID,
    min_role: EffectiveRole,
) -> EffectiveRole:
    """Return effective role if caller has at least ``min_role``."""
    role = await resolve_wiki_role(session, wiki, user_id)
    if role is None:
        raise NotFoundError("wiki not found")
    if _RANK[role] < _RANK[min_role]:
        raise ForbiddenError(f"requires {min_role} role")
    return role
