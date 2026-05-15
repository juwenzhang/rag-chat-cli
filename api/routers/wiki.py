"""Wiki layer: wikis (knowledge bases) + their pages.

URL space::

    /orgs/{org_id}/wikis              list / create wikis in a workspace
    /wikis/{wiki_id}                  get / update / delete a wiki
    /wikis/{wiki_id}/members          list / add wiki members (private only)
    /wikis/{wiki_id}/members/{uid}    update role / remove member
    /wikis/{wiki_id}/pages            list / create pages in a wiki
    /wiki-pages/{page_id}             get / update / delete a page
    /wiki-pages/{page_id}/duplicate   duplicate inside same wiki
    /wiki-pages/{page_id}/move        move to another wiki / re-parent

Permission resolution:

* ``org owner``                       — full read + write on every wiki
* ``org_wide`` wiki (the default)     — org members inherit their role
* ``private`` wiki                    — only explicit wiki_members (+ org
                                        owner) get in
"""

from __future__ import annotations

import re
import secrets
import string
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db_session
from api.routers.orgs import get_membership as get_org_membership
from api.routers.orgs import require_role as require_org_role
from api.schemas.wiki import (
    WikiCreateIn,
    WikiMemberAddIn,
    WikiMemberOut,
    WikiMemberRoleUpdateIn,
    WikiOut,
    WikiPageCreateIn,
    WikiPageDetailOut,
    WikiPageListOut,
    WikiPageMoveIn,
    WikiPageShareOut,
    WikiPageSharePublicOut,
    WikiPageUpdateIn,
    WikiUpdateIn,
)
from db.models import Org, User, Wiki, WikiMember, WikiPage, WikiPageShare

__all__ = ["router"]

router = APIRouter(tags=["wiki"])


# ─────────────────────────────────────────────────────────────────────
# Permission helpers — single source of truth for access decisions.
# ─────────────────────────────────────────────────────────────────────

EffectiveRole = Literal["owner", "editor", "viewer"]
_RANK = {"viewer": 1, "editor": 2, "owner": 3}


async def _resolve_wiki_role(
    session: AsyncSession, wiki: Wiki, user_id: uuid.UUID
) -> EffectiveRole | None:
    """Return the caller's effective role in ``wiki`` or ``None`` if no
    access.

    Resolution order:

    1. Org owner → ``owner`` (workspace boss always wins).
    2. ``visibility == "private"`` → only explicit wiki_members get
       through. The org owner already short-circuited in step 1.
    3. ``visibility == "org_wide"`` → org membership role propagates
       (with the small twist that org viewers see wikis read-only).
    """
    org = await session.get(Org, wiki.org_id)
    if org is None:
        return None  # dangling — should be impossible thanks to CASCADE
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

    # org_wide path
    if org_member is None:
        return None
    return org_member.role  # type: ignore[return-value]


async def _require_wiki_role(
    session: AsyncSession,
    wiki: Wiki,
    user_id: uuid.UUID,
    min_role: EffectiveRole,
) -> EffectiveRole:
    role = await _resolve_wiki_role(session, wiki, user_id)
    if role is None:
        # 404 (not 403) so we don't leak the wiki's existence.
        raise HTTPException(status_code=404, detail="wiki not found")
    if _RANK[role] < _RANK[min_role]:
        raise HTTPException(
            status_code=403, detail=f"requires {min_role} role"
        )
    return role


def _to_wiki_out(wiki: Wiki, role: EffectiveRole) -> WikiOut:
    return WikiOut(
        id=wiki.id,
        org_id=wiki.org_id,
        slug=wiki.slug,
        name=wiki.name,
        description=wiki.description,
        created_by_user_id=wiki.created_by_user_id,
        is_default=wiki.is_default,
        visibility=wiki.visibility,  # type: ignore[arg-type]
        created_at=wiki.created_at,
        updated_at=wiki.updated_at,
        role=role,
    )


_SLUG_FALLBACK_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = _SLUG_FALLBACK_RE.sub("", s)
    s = s.strip("-")
    return s[:48] or "wiki"


# ─────────────────────────────────────────────────────────────────────
# Wikis (knowledge bases)
# ─────────────────────────────────────────────────────────────────────


@router.get(
    "/orgs/{org_id}/wikis",
    response_model=list[WikiOut],
    summary="List wikis I can see in a workspace",
)
async def list_wikis(
    org_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[WikiOut]:
    # Must at least be in the org to see anything.
    await require_org_role(session, org_id, user.id, "viewer")
    rows = (
        await session.execute(
            select(Wiki)
            .where(Wiki.org_id == org_id)
            .order_by(Wiki.is_default.desc(), Wiki.created_at.asc())
        )
    ).scalars().all()
    out: list[WikiOut] = []
    for w in rows:
        role = await _resolve_wiki_role(session, w, user.id)
        if role is None:
            # Private wiki the user isn't a member of — skip silently.
            continue
        out.append(_to_wiki_out(w, role))
    return out


@router.post(
    "/orgs/{org_id}/wikis",
    response_model=WikiOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new wiki inside a workspace",
)
async def create_wiki(
    org_id: uuid.UUID,
    body: WikiCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WikiOut:
    # Editor or above in the org may add new wikis.
    await require_org_role(session, org_id, user.id, "editor")
    base_slug = body.slug or _slugify(body.name)
    slug = base_slug
    suffix = 2
    while await session.scalar(
        select(Wiki.id).where(Wiki.org_id == org_id, Wiki.slug == slug)
    ):
        slug = f"{base_slug}-{suffix}"[:64]
        suffix += 1
        if suffix > 50:
            raise HTTPException(
                status_code=409, detail="couldn't allocate a unique slug"
            )
    wiki = Wiki(
        org_id=org_id,
        slug=slug,
        name=body.name,
        description=body.description,
        created_by_user_id=user.id,
        is_default=False,
        visibility=body.visibility,
    )
    session.add(wiki)
    # If private, seed the creator as an editor so the wiki isn't
    # immediately invisible to them (org owners would still see it via
    # the role-resolution short-circuit, but non-owner creators need an
    # explicit row).
    if body.visibility == "private":
        await session.flush()
        session.add(
            WikiMember(wiki_id=wiki.id, user_id=user.id, role="editor")
        )
    await session.commit()
    await session.refresh(wiki)
    role = await _resolve_wiki_role(session, wiki, user.id)
    assert role is not None
    return _to_wiki_out(wiki, role)


@router.get(
    "/wikis/{wiki_id}",
    response_model=WikiOut,
    summary="Get one wiki",
)
async def get_wiki(
    wiki_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WikiOut:
    wiki = await session.get(Wiki, wiki_id)
    if wiki is None:
        raise HTTPException(status_code=404, detail="wiki not found")
    role = await _require_wiki_role(session, wiki, user.id, "viewer")
    return _to_wiki_out(wiki, role)


@router.patch(
    "/wikis/{wiki_id}",
    response_model=WikiOut,
    summary="Rename / re-describe / change visibility",
)
async def update_wiki(
    wiki_id: uuid.UUID,
    body: WikiUpdateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WikiOut:
    wiki = await session.get(Wiki, wiki_id)
    if wiki is None:
        raise HTTPException(status_code=404, detail="wiki not found")
    # Only org owner / editor (or anyone who's editor on the wiki itself)
    # may rename. We piggyback on _require_wiki_role for that check.
    await _require_wiki_role(session, wiki, user.id, "editor")
    if body.name is not None:
        wiki.name = body.name
    if body.description is not None:
        wiki.description = body.description
    if body.visibility is not None and body.visibility != wiki.visibility:
        # Promoting org_wide → private: seed all org editors+ as wiki
        # editors so they don't suddenly lose access. (Viewers don't
        # carry over — org_wide gave them read access for free, but the
        # whole point of going private is to tighten.)
        if wiki.visibility == "org_wide" and body.visibility == "private":
            # Already a member? skip. Otherwise seed.
            from db.models import OrgMember

            org_editors = (
                await session.execute(
                    select(OrgMember).where(
                        OrgMember.org_id == wiki.org_id,
                        OrgMember.role.in_(("owner", "editor")),
                    )
                )
            ).scalars().all()
            for m in org_editors:
                existing = await session.scalar(
                    select(WikiMember).where(
                        WikiMember.wiki_id == wiki.id,
                        WikiMember.user_id == m.user_id,
                    )
                )
                if existing is None:
                    session.add(
                        WikiMember(
                            wiki_id=wiki.id,
                            user_id=m.user_id,
                            role="editor",
                        )
                    )
        wiki.visibility = body.visibility
    await session.commit()
    await session.refresh(wiki)
    role = await _resolve_wiki_role(session, wiki, user.id)
    assert role is not None
    return _to_wiki_out(wiki, role)


@router.delete(
    "/wikis/{wiki_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a wiki (refuses the default wiki)",
)
async def delete_wiki(
    wiki_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    wiki = await session.get(Wiki, wiki_id)
    if wiki is None:
        raise HTTPException(status_code=404, detail="wiki not found")
    # Hard gate: only org owner may delete a wiki (it's destructive and
    # cascades all pages). ``is_default`` is no longer enforced as a
    # deletion guard since fresh orgs no longer auto-provision one —
    # the flag is kept on the row only as historical metadata.
    await require_org_role(session, wiki.org_id, user.id, "owner")
    await session.delete(wiki)
    await session.commit()


# ─────────────────────────────────────────────────────────────────────
# Wiki members (only meaningful for ``private`` wikis)
# ─────────────────────────────────────────────────────────────────────


def _member_to_out(member: WikiMember, target_user: User) -> WikiMemberOut:
    return WikiMemberOut(
        user_id=target_user.id,
        email=target_user.email,
        display_name=target_user.display_name,
        role=member.role,  # type: ignore[arg-type]
        created_at=member.created_at,
    )


@router.get(
    "/wikis/{wiki_id}/members",
    response_model=list[WikiMemberOut],
    summary="List wiki members",
)
async def list_wiki_members(
    wiki_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[WikiMemberOut]:
    wiki = await session.get(Wiki, wiki_id)
    if wiki is None:
        raise HTTPException(status_code=404, detail="wiki not found")
    await _require_wiki_role(session, wiki, user.id, "viewer")
    rows = (
        await session.execute(
            select(WikiMember, User)
            .join(User, User.id == WikiMember.user_id)
            .where(WikiMember.wiki_id == wiki_id)
            .order_by(WikiMember.created_at.asc())
        )
    ).all()
    return [_member_to_out(m, u) for m, u in rows]


@router.post(
    "/wikis/{wiki_id}/members",
    response_model=WikiMemberOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a wiki member (only meaningful for private wikis)",
)
async def add_wiki_member(
    wiki_id: uuid.UUID,
    body: WikiMemberAddIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WikiMemberOut:
    wiki = await session.get(Wiki, wiki_id)
    if wiki is None:
        raise HTTPException(status_code=404, detail="wiki not found")
    # Only the org owner manages wiki members (avoids "editor invites a
    # viewer who then has equal power" surprises). Org-wide wikis don't
    # actually use this table, but we still accept rows — they take
    # effect only if the wiki later goes private.
    await require_org_role(session, wiki.org_id, user.id, "owner")
    target = await session.scalar(
        select(User).where(User.email == body.email.lower())
    )
    if target is None:
        raise HTTPException(status_code=404, detail="no user with that email")
    existing = await session.scalar(
        select(WikiMember).where(
            WikiMember.wiki_id == wiki_id,
            WikiMember.user_id == target.id,
        )
    )
    if existing is not None:
        existing.role = body.role
        await session.commit()
        return _member_to_out(existing, target)
    member = WikiMember(wiki_id=wiki_id, user_id=target.id, role=body.role)
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return _member_to_out(member, target)


@router.patch(
    "/wikis/{wiki_id}/members/{user_id}",
    response_model=WikiMemberOut,
    summary="Change a wiki member's role",
)
async def update_wiki_member(
    wiki_id: uuid.UUID,
    user_id: uuid.UUID,
    body: WikiMemberRoleUpdateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WikiMemberOut:
    wiki = await session.get(Wiki, wiki_id)
    if wiki is None:
        raise HTTPException(status_code=404, detail="wiki not found")
    await require_org_role(session, wiki.org_id, user.id, "owner")
    target = await session.scalar(
        select(WikiMember).where(
            WikiMember.wiki_id == wiki_id, WikiMember.user_id == user_id
        )
    )
    if target is None:
        raise HTTPException(status_code=404, detail="member not found")
    target.role = body.role
    await session.commit()
    target_user = await session.get(User, user_id)
    assert target_user is not None
    return _member_to_out(target, target_user)


@router.delete(
    "/wikis/{wiki_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a wiki member (self-removal allowed)",
)
async def remove_wiki_member(
    wiki_id: uuid.UUID,
    user_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    wiki = await session.get(Wiki, wiki_id)
    if wiki is None:
        raise HTTPException(status_code=404, detail="wiki not found")
    if user_id == user.id:
        # Self-removal: any current member can leave.
        await _require_wiki_role(session, wiki, user.id, "viewer")
    else:
        await require_org_role(session, wiki.org_id, user.id, "owner")
    target = await session.scalar(
        select(WikiMember).where(
            WikiMember.wiki_id == wiki_id, WikiMember.user_id == user_id
        )
    )
    if target is None:
        raise HTTPException(status_code=404, detail="member not found")
    await session.delete(target)
    await session.commit()


# ─────────────────────────────────────────────────────────────────────
# Wiki pages
# ─────────────────────────────────────────────────────────────────────


@router.get(
    "/wikis/{wiki_id}/pages",
    response_model=list[WikiPageListOut],
    summary="List pages in a wiki",
)
async def list_pages(
    wiki_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[WikiPageListOut]:
    wiki = await session.get(Wiki, wiki_id)
    if wiki is None:
        raise HTTPException(status_code=404, detail="wiki not found")
    await _require_wiki_role(session, wiki, user.id, "viewer")
    rows = (
        await session.execute(
            select(WikiPage)
            .where(WikiPage.wiki_id == wiki_id)
            .order_by(WikiPage.position.asc(), WikiPage.updated_at.desc())
        )
    ).scalars().all()
    return [WikiPageListOut.model_validate(r) for r in rows]


@router.post(
    "/wikis/{wiki_id}/pages",
    response_model=WikiPageDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a page inside a wiki",
)
async def create_page(
    wiki_id: uuid.UUID,
    body: WikiPageCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WikiPageDetailOut:
    wiki = await session.get(Wiki, wiki_id)
    if wiki is None:
        raise HTTPException(status_code=404, detail="wiki not found")
    await _require_wiki_role(session, wiki, user.id, "editor")

    if body.parent_id is not None:
        parent = await session.get(WikiPage, body.parent_id)
        if parent is None or parent.wiki_id != wiki_id:
            raise HTTPException(
                status_code=400,
                detail="parent must be a page in this wiki",
            )

    next_pos = await session.scalar(
        select(WikiPage.position)
        .where(WikiPage.wiki_id == wiki_id, WikiPage.parent_id == body.parent_id)
        .order_by(WikiPage.position.desc())
        .limit(1)
    )

    page = WikiPage(
        wiki_id=wiki_id,
        created_by_user_id=user.id,
        parent_id=body.parent_id,
        title=body.title or "Untitled",
        body=body.body or "",
        position=(next_pos or 0) + 1,
        revision=1,
    )
    session.add(page)
    await session.commit()
    await session.refresh(page)
    return WikiPageDetailOut.model_validate(page)


async def _page_with_access(
    session: AsyncSession,
    page_id: uuid.UUID,
    user_id: uuid.UUID,
    min_role: EffectiveRole,
) -> tuple[WikiPage, Wiki, EffectiveRole]:
    """Resolve a page + its wiki and verify caller access."""
    page = await session.get(WikiPage, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="page not found")
    wiki = await session.get(Wiki, page.wiki_id)
    if wiki is None:
        raise HTTPException(status_code=404, detail="page not found")
    role = await _require_wiki_role(session, wiki, user_id, min_role)
    return page, wiki, role


@router.get(
    "/wiki-pages/{page_id}",
    response_model=WikiPageDetailOut,
    summary="Get a page",
)
async def get_page(
    page_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WikiPageDetailOut:
    page, _wiki, _role = await _page_with_access(
        session, page_id, user.id, "viewer"
    )
    return WikiPageDetailOut.model_validate(page)


@router.patch(
    "/wiki-pages/{page_id}",
    response_model=WikiPageDetailOut,
    summary="Update a page (optimistic concurrency via revision)",
)
async def update_page(
    page_id: uuid.UUID,
    body: WikiPageUpdateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WikiPageDetailOut:
    page, _wiki, _role = await _page_with_access(
        session, page_id, user.id, "editor"
    )
    if body.revision != page.revision:
        raise HTTPException(
            status_code=409,
            detail="page changed elsewhere; reload to continue",
            headers={"X-Server-Revision": str(page.revision)},
        )
    if body.title is not None:
        page.title = body.title
    if body.body is not None:
        page.body = body.body
    if body.parent_id is not None:
        page.parent_id = body.parent_id
    page.revision += 1
    await session.commit()
    await session.refresh(page)
    return WikiPageDetailOut.model_validate(page)


@router.delete(
    "/wiki-pages/{page_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a page",
)
async def delete_page(
    page_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    page, _wiki, _role = await _page_with_access(
        session, page_id, user.id, "editor"
    )
    await session.delete(page)
    await session.commit()


@router.post(
    "/wiki-pages/{page_id}/duplicate",
    response_model=WikiPageDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate a page inside the same wiki",
)
async def duplicate_page(
    page_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WikiPageDetailOut:
    src, _wiki, _role = await _page_with_access(
        session, page_id, user.id, "editor"
    )
    next_pos = await session.scalar(
        select(WikiPage.position)
        .where(
            WikiPage.wiki_id == src.wiki_id,
            WikiPage.parent_id == src.parent_id,
        )
        .order_by(WikiPage.position.desc())
        .limit(1)
    )
    copy = WikiPage(
        wiki_id=src.wiki_id,
        created_by_user_id=user.id,
        parent_id=src.parent_id,
        title=f"{src.title} (copy)",
        body=src.body,
        position=(next_pos or 0) + 1,
        revision=1,
    )
    session.add(copy)
    await session.commit()
    await session.refresh(copy)
    return WikiPageDetailOut.model_validate(copy)


@router.post(
    "/wiki-pages/{page_id}/move",
    response_model=WikiPageDetailOut,
    summary="Move a page to another wiki and/or re-parent it",
)
async def move_page(
    page_id: uuid.UUID,
    body: WikiPageMoveIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WikiPageDetailOut:
    if body.target_wiki_id is None and body.new_parent_id is None:
        raise HTTPException(
            status_code=400,
            detail="target_wiki_id or new_parent_id required",
        )
    page, _wiki, _role = await _page_with_access(
        session, page_id, user.id, "editor"
    )

    if body.target_wiki_id is not None and body.target_wiki_id != page.wiki_id:
        # Need editor in the destination wiki too.
        target_wiki = await session.get(Wiki, body.target_wiki_id)
        if target_wiki is None:
            raise HTTPException(
                status_code=400, detail="destination wiki not found"
            )
        await _require_wiki_role(session, target_wiki, user.id, "editor")
        page.wiki_id = body.target_wiki_id
        # Moving across wikis invalidates the parent reference.
        page.parent_id = None

    if body.new_parent_id is not None:
        if body.new_parent_id == page.id:
            raise HTTPException(
                status_code=400, detail="page cannot be its own parent"
            )
        parent = await session.get(WikiPage, body.new_parent_id)
        if parent is None or parent.wiki_id != page.wiki_id:
            raise HTTPException(
                status_code=400,
                detail="parent must exist in the same wiki",
            )
        # Cycle check.
        cursor: WikiPage | None = parent
        while cursor is not None and cursor.parent_id is not None:
            if cursor.parent_id == page.id:
                raise HTTPException(
                    status_code=400, detail="move would create a cycle"
                )
            cursor = await session.get(WikiPage, cursor.parent_id)
        page.parent_id = body.new_parent_id

    next_pos = await session.scalar(
        select(WikiPage.position)
        .where(
            WikiPage.wiki_id == page.wiki_id,
            WikiPage.parent_id == page.parent_id,
            WikiPage.id != page.id,
        )
        .order_by(WikiPage.position.desc())
        .limit(1)
    )
    page.position = (next_pos or 0) + 1

    await session.commit()
    await session.refresh(page)
    return WikiPageDetailOut.model_validate(page)


# ─────────────────────────────────────────────────────────────────────
# Wiki page shares — public links to individual pages
# ─────────────────────────────────────────────────────────────────────

_TOKEN_ALPHABET = string.ascii_letters + string.digits
_TOKEN_LEN = 16


def _new_token() -> str:
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(_TOKEN_LEN))


@router.post(
    "/wiki-pages/{page_id}/share",
    response_model=WikiPageShareOut,
    status_code=status.HTTP_201_CREATED,
    summary="Share a wiki page (get-or-create by (user, page_id))",
)
async def create_page_share(
    page_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WikiPageShareOut:
    page, _wiki, _role = await _page_with_access(
        session, page_id, user.id, "viewer"
    )

    existing = await session.scalar(
        select(WikiPageShare).where(
            WikiPageShare.user_id == user.id,
            WikiPageShare.page_id == page.id,
        )
    )
    if existing is not None:
        return WikiPageShareOut.model_validate(existing)

    row = WikiPageShare(
        token=_new_token(),
        user_id=user.id,
        page_id=page.id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return WikiPageShareOut.model_validate(row)


@router.get(
    "/wiki-pages/{page_id}/share",
    response_model=WikiPageShareOut,
    summary="Get the current user's share for this page (if any)",
)
async def get_page_share(
    page_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WikiPageShareOut:
    await _page_with_access(session, page_id, user.id, "viewer")

    row = await session.scalar(
        select(WikiPageShare).where(
            WikiPageShare.user_id == user.id,
            WikiPageShare.page_id == page_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="no share for this page")
    return WikiPageShareOut.model_validate(row)


@router.delete(
    "/wiki-page-shares/{token}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a wiki page share by token (owner only)",
)
async def revoke_page_share(
    token: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    row = await session.scalar(
        select(WikiPageShare).where(WikiPageShare.token == token)
    )
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="share not found")
    await session.delete(row)
    await session.commit()


@router.get(
    "/wiki-page-shares/{token}",
    response_model=WikiPageSharePublicOut,
    summary="Public — fetch a shared wiki page by token (no auth required)",
)
async def public_page_share(
    token: str,
    session: AsyncSession = Depends(get_db_session),
) -> WikiPageSharePublicOut:
    row = await session.scalar(
        select(WikiPageShare).where(WikiPageShare.token == token)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="share not found")

    page = await session.get(WikiPage, row.page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="share content unavailable")

    wiki = await session.get(Wiki, page.wiki_id)
    wiki_name = wiki.name if wiki else "Unknown"

    sharer = await session.get(User, row.user_id)
    shared_by = sharer.display_name if sharer else None

    return WikiPageSharePublicOut(
        token=row.token,
        created_at=row.created_at,
        page_id=row.page_id,
        page_title=page.title,
        page_body=page.body,
        wiki_name=wiki_name,
        shared_by_display_name=shared_by,
    )
