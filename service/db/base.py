"""Declarative base with a predictable naming convention.

Why a naming convention?
    Alembic ``autogenerate`` produces deterministic constraint names only
    when a :class:`MetaData` naming convention is set. This keeps
    migrations reproducible across developers and machines.

The convention below is the one recommended by the SQLAlchemy manual.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

__all__ = ["NAMING_CONVENTION", "Base"]


NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Project-wide declarative base. All ORM models inherit from this."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
