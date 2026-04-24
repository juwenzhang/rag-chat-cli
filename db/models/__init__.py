"""Model re-exports.

Importing this package is the single point that forces every ORM class
to register itself with :data:`db.base.Base.metadata`. Alembic
``autogenerate`` and our ``conftest.py`` fixture both rely on this
side-effect::

    import db.models  # ensure all tables are registered
    from db.base import Base
    metadata = Base.metadata
"""

from __future__ import annotations

from db.models.chunk import Chunk
from db.models.document import Document
from db.models.message import Message
from db.models.session import ChatSession
from db.models.token import RefreshToken
from db.models.user import User

__all__ = [
    "ChatSession",
    "Chunk",
    "Document",
    "Message",
    "RefreshToken",
    "User",
]
