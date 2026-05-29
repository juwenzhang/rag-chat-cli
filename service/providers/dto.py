"""Provider DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from service.db.models import Provider

__all__ = ["ProviderInfo"]


@dataclass(frozen=True, slots=True)
class ProviderInfo:
    """Safe projection of a provider row without plaintext credentials."""

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    type: str
    base_url: str
    has_api_key: bool
    is_default: bool
    enabled: bool

    @classmethod
    def from_row(cls, row: Provider) -> ProviderInfo:
        return cls(
            id=row.id,
            user_id=row.user_id,
            name=row.name,
            type=row.type,
            base_url=row.base_url,
            has_api_key=bool(row.api_key_encrypted),
            is_default=row.is_default,
            enabled=row.enabled,
        )
