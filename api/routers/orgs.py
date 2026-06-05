"""``/orgs`` — workspaces and their memberships.

Permission model:

* **owner**  — full control: rename, delete, manage members, read/write
  all wiki pages.
* **editor** — read + write wiki pages, cannot change membership.
* **viewer** — read-only.

The auto-provisioned per-user *personal* org (``is_personal=true``)
cannot be deleted — that would orphan the user's default workspace.
Renaming it is fine.
"""

from __future__ import annotations

import re
import uuid
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db_session
from api.schemas.org import (
    MemberAddIn,
    MemberOut,
    MemberRoleUpdateIn,
    OrgCreateIn,
    OrgOut,
    OrgTransferIn,
    OrgUpdateIn,
    Role,
)
from service.core.errors import ForbiddenError, NotFoundError
from service.db.models import Org, OrgMember, User
from service.orgs.policy import get_membership as service_get_membership
from service.orgs.policy import require_role as service_require_role

__all__ = ["router"]

router = APIRouter(tags=["orgs"])


# ── Authorization adapters ───────────────────────────────────────────


async def _get_membership(
    session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
) -> OrgMember | None:
    return await service_get_membership(session, org_id, user_id)


async def _require_role(
    session: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    min_role: str,
) -> OrgMember:
    try:
        return await service_require_role(session, org_id, user_id, min_role)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail="org not found") from exc
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _to_out(org: Org, role: str) -> OrgOut:
    return OrgOut(
        id=org.id,
        slug=org.slug,
        name=org.name,
        owner_id=org.owner_id,
        is_personal=org.is_personal,
        created_at=org.created_at,
        updated_at=org.updated_at,
        # DB stores ``role`` as plain ``str``; the column is constrained
        # to the Role literals at the application layer, so the cast is
        # the right place to narrow once for the whole router.
        role=cast(Role, role),
    )


_SLUG_FALLBACK_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(name: str) -> str:
    """Crude deterministic slug — lowercase, spaces→hyphens, strip other chars.

    Collisions are resolved at insert time by appending ``-<n>`` until
    we find a free one. 64-char cap matches the column.
    """
    s = name.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = _SLUG_FALLBACK_RE.sub("", s)
    s = s.strip("-")
    return s[:48] or "workspace"


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/orgs", response_model=list[OrgOut], summary="List my orgs")
async def list_orgs(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[OrgOut]:
    rows = (
        await session.execute(
            select(Org, OrgMember.role)
            .join(OrgMember, OrgMember.org_id == Org.id)
            .where(OrgMember.user_id == user.id)
            .order_by(Org.is_personal.desc(), Org.created_at.asc())
        )
    ).all()
    return [_to_out(org, role) for org, role in rows]


@router.post(
    "/orgs",
    response_model=OrgOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new org (caller becomes owner)",
)
async def create_org(
    body: OrgCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OrgOut:
    base_slug = body.slug or _slugify(body.name)
    # Resolve a free slug by suffixing ``-<n>``. The unique constraint
    # is what we ultimately trust; this is just a friendlier UX.
    slug = base_slug
    suffix = 2
    while await session.scalar(select(Org.id).where(Org.slug == slug)):
        slug = f"{base_slug}-{suffix}"[:64]
        suffix += 1
        if suffix > 50:
            raise HTTPException(status_code=409, detail="couldn't allocate a unique slug")
    org = Org(slug=slug, name=body.name, owner_id=user.id, is_personal=False)
    session.add(org)
    await session.flush()
    session.add(OrgMember(org_id=org.id, user_id=user.id, role="owner"))
    # We intentionally don't auto-provision a wiki here — users create
    # wikis explicitly so the RAG scope (per-wiki) stays intentional.
    await session.commit()
    await session.refresh(org)
    return _to_out(org, "owner")


@router.get("/orgs/{org_id}", response_model=OrgOut, summary="Get one org")
async def get_org(
    org_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OrgOut:
    member = await _require_role(session, org_id, user.id, "viewer")
    org = await session.get(Org, org_id)
    assert org is not None  # require_role already proved membership
    return _to_out(org, member.role)


@router.patch("/orgs/{org_id}", response_model=OrgOut, summary="Rename an org")
async def update_org(
    org_id: uuid.UUID,
    body: OrgUpdateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OrgOut:
    member = await _require_role(session, org_id, user.id, "owner")
    org = await session.get(Org, org_id)
    assert org is not None
    if body.name is not None:
        org.name = body.name
    await session.commit()
    await session.refresh(org)
    return _to_out(org, member.role)


@router.delete(
    "/orgs/{org_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an org (refuses personal orgs)",
)
async def delete_org(
    org_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await _require_role(session, org_id, user.id, "owner")
    org = await session.get(Org, org_id)
    assert org is not None
    if org.is_personal:
        raise HTTPException(status_code=400, detail="cannot delete a personal org")
    await session.delete(org)
    await session.commit()


# ── Members ──────────────────────────────────────────────────────────


def _member_to_out(member: OrgMember, target_user: User) -> MemberOut:
    return MemberOut(
        user_id=target_user.id,
        email=target_user.email,
        display_name=target_user.display_name,
        role=cast(Role, member.role),
        created_at=member.created_at,
    )


@router.get(
    "/orgs/{org_id}/members",
    response_model=list[MemberOut],
    summary="List org members",
)
async def list_members(
    org_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[MemberOut]:
    await _require_role(session, org_id, user.id, "viewer")
    rows = (
        await session.execute(
            select(OrgMember, User)
            .join(User, User.id == OrgMember.user_id)
            .where(OrgMember.org_id == org_id)
            .order_by(OrgMember.created_at.asc())
        )
    ).all()
    return [_member_to_out(m, u) for m, u in rows]


@router.post(
    "/orgs/{org_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
    summary="Invite an existing user by email",
)
async def add_member(
    org_id: uuid.UUID,
    body: MemberAddIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MemberOut:
    await _require_role(session, org_id, user.id, "owner")
    target = await session.scalar(select(User).where(User.email == body.email.lower()))
    if target is None:
        raise HTTPException(status_code=404, detail="no user with that email")
    existing = await _get_membership(session, org_id, target.id)
    if existing is not None:
        # Idempotent: re-inviting an existing member updates their role.
        existing.role = body.role
        await session.commit()
        return _member_to_out(existing, target)
    member = OrgMember(org_id=org_id, user_id=target.id, role=body.role)
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return _member_to_out(member, target)


@router.patch(
    "/orgs/{org_id}/members/{user_id}",
    response_model=MemberOut,
    summary="Change a member's role",
)
async def update_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: MemberRoleUpdateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MemberOut:
    await _require_role(session, org_id, user.id, "owner")
    target = await _get_membership(session, org_id, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="member not found")
    org = await session.get(Org, org_id)
    assert org is not None
    if target.user_id == org.owner_id and body.role != "owner":
        # Demoting the org owner without naming a replacement leaves the
        # org without anyone who can manage it. Refuse — the UI should
        # promote someone else first.
        raise HTTPException(
            status_code=400,
            detail="cannot demote the org owner; transfer ownership first",
        )
    target.role = body.role
    await session.commit()
    target_user = await session.get(User, user_id)
    assert target_user is not None
    return _member_to_out(target, target_user)


@router.delete(
    "/orgs/{org_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member (or leave the org if removing yourself)",
)
async def remove_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    # Self-removal needs only viewer role; removing others needs owner.
    if user_id == user.id:
        await _require_role(session, org_id, user.id, "viewer")
    else:
        await _require_role(session, org_id, user.id, "owner")
    target = await _get_membership(session, org_id, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="member not found")
    org = await session.get(Org, org_id)
    assert org is not None
    if target.user_id == org.owner_id:
        raise HTTPException(
            status_code=400,
            detail="cannot remove the org owner; transfer ownership first",
        )
    await session.delete(target)
    await session.commit()


@router.post(
    "/orgs/{org_id}/transfer",
    response_model=OrgOut,
    summary="Transfer ownership to another member (previous owner becomes editor)",
)
async def transfer_ownership(
    org_id: uuid.UUID,
    body: OrgTransferIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OrgOut:
    await _require_role(session, org_id, user.id, "owner")
    org = await session.get(Org, org_id)
    assert org is not None
    if body.new_owner_id == user.id:
        raise HTTPException(status_code=400, detail="you're already the owner")
    if org.is_personal:
        raise HTTPException(
            status_code=400,
            detail="cannot transfer a personal org",
        )
    target = await _get_membership(session, org_id, body.new_owner_id)
    if target is None:
        raise HTTPException(status_code=404, detail="target user is not a member")
    prev_owner = await _get_membership(session, org_id, user.id)
    assert prev_owner is not None

    # Demote outgoing owner first so the (org_id, role=owner) invariant
    # never holds two rows simultaneously inside the transaction.
    prev_owner.role = "editor"
    target.role = "owner"
    org.owner_id = body.new_owner_id
    await session.commit()
    await session.refresh(org)
    # The caller's role in the org has changed — return what the caller
    # now sees so the client doesn't have to refetch.
    return _to_out(org, "editor")
