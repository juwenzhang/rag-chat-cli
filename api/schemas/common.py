"""Cross-cutting DTOs: pagination, error envelope, OK ack.

Pydantic v2 generics (``BaseModel`` + :class:`typing.Generic`) produce proper
``anyOf`` schemas in the OpenAPI dump, so ``Page[UserOut]`` shows up with its
items typed correctly.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ErrorResponse", "OkResponse", "Page"]

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Cursor-free page container. Uses ``page`` + ``size`` + ``total``."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[T]
    page: int = Field(ge=1)
    size: int = Field(ge=1, le=200)
    total: int = Field(ge=0)


class ErrorResponse(BaseModel):
    """Canonical 4xx/5xx body (AGENTS.md §5)."""

    code: str
    message: str
    request_id: str | None = None
    details: dict[str, Any] | None = None


class OkResponse(BaseModel):
    """Boolean acknowledgement — used for ``202`` or delete-like endpoints."""

    ok: bool = True
