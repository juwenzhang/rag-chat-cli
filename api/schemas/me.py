"""DTOs backing the ``/me`` endpoints."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

__all__ = ["UserPatchIn"]


class UserPatchIn(BaseModel):
    """Whitelist of fields patchable via ``PATCH /me``.

    We deliberately do NOT expose ``email`` / ``is_active`` / ``password``
    here — those have dedicated flows (or plain "not supported yet").
    """

    display_name: Annotated[str, Field(min_length=1, max_length=64)] | None = None
