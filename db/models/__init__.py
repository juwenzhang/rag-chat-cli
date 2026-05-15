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
from db.models.message_bookmark import MessageBookmark
from db.models.message_share import MessageShare
from db.models.model_metadata import ModelMetadata
from db.models.org import Org
from db.models.org_member import OrgMember
from db.models.preference import UserPreference
from db.models.provider import Provider
from db.models.session import ChatSession
from db.models.token import RefreshToken
from db.models.user import User
from db.models.user_memory import UserMemory
from db.models.wiki import Wiki
from db.models.wiki_member import WikiMember
from db.models.wiki_page import WikiPage
from db.models.wiki_page_share import WikiPageShare

__all__ = [
    "ChatSession",
    "Chunk",
    "Document",
    "Message",
    "MessageBookmark",
    "MessageShare",
    "ModelMetadata",
    "Org",
    "OrgMember",
    "Provider",
    "RefreshToken",
    "User",
    "UserMemory",
    "UserPreference",
    "Wiki",
    "WikiMember",
    "WikiPage",
    "WikiPageShare",
]
