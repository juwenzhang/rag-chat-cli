"""Model re-exports.

Importing this package is the single point that forces every ORM class
to register itself with :data:`db.base.Base.metadata`. Alembic
``autogenerate`` and our ``conftest.py`` fixture both rely on this
side-effect::

    import service.db.models  # ensure all tables are registered
    from service.db.base import Base
    metadata = Base.metadata
"""

from __future__ import annotations

from service.db.models.asset import Asset
from service.db.models.chunk import Chunk
from service.db.models.document import Document
from service.db.models.message import Message
from service.db.models.message_bookmark import MessageBookmark
from service.db.models.message_share import MessageShare
from service.db.models.model_metadata import ModelMetadata
from service.db.models.org import Org
from service.db.models.org_member import OrgMember
from service.db.models.preference import UserPreference
from service.db.models.provider import Provider
from service.db.models.session import ChatSession
from service.db.models.token import RefreshToken
from service.db.models.user import User
from service.db.models.user_memory import UserMemory
from service.db.models.wiki import Wiki
from service.db.models.wiki_member import WikiMember
from service.db.models.wiki_page import WikiPage
from service.db.models.wiki_page_share import WikiPageShare

__all__ = [
    "Asset",
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
