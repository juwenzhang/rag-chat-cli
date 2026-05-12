"""Per-user LLM provider registry.

One row = one configured endpoint (a local Ollama, an OpenAI key, an
OpenRouter key, …). Users can register many; one may be flagged
``is_default``. A row's ``api_key_encrypted`` is a Fernet ciphertext —
plaintext keys never live in the DB.

``type`` is a free-form lowercase string. Currently understood values:

* ``"ollama"`` — Ollama HTTP API (``/api/tags``, ``/api/chat`` …).
* ``"openai"`` — OpenAI-compatible (``/v1/models``, ``/v1/chat/completions``);
  covers OpenAI, OpenRouter, Together, DeepSeek, Groq, …

Adding a new provider type means teaching ``core.providers`` to dispatch on
this string — no schema migration needed.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["Provider"]


class Provider(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "providers"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_providers_user_id_name"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    # NULL for keyless backends (local Ollama on the default port).
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
