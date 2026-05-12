"""Provider / preference DTOs (Sprint 2).

Mirrors :class:`core.providers.ProviderInfo`. The ``api_key`` plaintext only
appears in *request* DTOs — responses expose ``has_api_key`` instead so
plaintext keys never leave the server.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

__all__ = [
    "ConnectivityTestIn",
    "ConnectivityTestOut",
    "ModelListItem",
    "ProviderCreateIn",
    "ProviderOut",
    "ProviderUpdateIn",
    "UserPreferenceIn",
    "UserPreferenceOut",
]


ProviderType = Literal["ollama", "openai"]


class ProviderCreateIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=64)]
    type: ProviderType
    base_url: HttpUrl
    api_key: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    is_default: bool = False
    # If True (default), refuse to create when the URL/key combo can't be
    # reached. Set False to register an offline provider for later use.
    test_connectivity: bool = True


class ProviderUpdateIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    base_url: HttpUrl | None = None
    # ``api_key`` is sentinel-aware: ``None`` (default) means "don't touch";
    # set ``clear_api_key=True`` to wipe an existing key.
    api_key: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    clear_api_key: bool = False
    is_default: bool | None = None
    enabled: bool | None = None


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    base_url: str
    has_api_key: bool
    is_default: bool
    enabled: bool


class ConnectivityTestIn(BaseModel):
    type: ProviderType
    base_url: HttpUrl
    api_key: Annotated[str, Field(max_length=512)] | None = None


class ConnectivityTestOut(BaseModel):
    ok: bool
    detail: str


class ModelListItem(BaseModel):
    id: str
    size: int | None = None


class UserPreferenceIn(BaseModel):
    default_provider_id: uuid.UUID | None = None
    default_model: Annotated[str, Field(max_length=128)] | None = None
    default_use_rag: bool | None = None
    # Sentinel: pass True to wipe the existing default_provider_id pin.
    clear_default_provider: bool = False
    clear_default_model: bool = False


class UserPreferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    default_provider_id: uuid.UUID | None
    default_model: str | None
    default_use_rag: bool
