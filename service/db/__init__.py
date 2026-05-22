"""Database layer — SQLAlchemy 2.x async + pgvector + Alembic.

Kept *intentionally empty* at the package level. Call sites import the
specific submodule they need::

    from service.db.base import Base
    from service.db.session import init_engine, get_session
    from service.db.models.user import User

This matches the pattern established by ``core/`` (see AGENTS.md §2).
"""

__all__: list[str] = []
