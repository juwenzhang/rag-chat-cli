"""Database URL helpers shared by runtime and Alembic."""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import make_url

__all__ = ["asyncpg_connect_args", "normalize_database_url"]


def normalize_database_url(url: str) -> str:
    """Return a SQLAlchemy URL safe for the configured driver.

    Neon/libpq connection strings commonly include query parameters such as
    ``sslmode=require`` and ``channel_binding=require``. SQLAlchemy's asyncpg
    dialect may pass those through as ``asyncpg.connect()`` kwargs in some
    versions, where they are not accepted. Runtime SSL is instead expressed via
    ``connect_args={"ssl": True}``, returned by :func:`asyncpg_connect_args`.
    """

    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg":
        return url

    query = dict(parsed.query)
    query.pop("sslmode", None)
    query.pop("channel_binding", None)
    return str(parsed.set(query=query))


def asyncpg_connect_args(url: str) -> dict[str, Any]:
    """Return driver connect args implied by a PostgreSQL asyncpg URL."""

    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg":
        return {}

    sslmode = parsed.query.get("sslmode")
    if sslmode is None:
        return {}

    mode = str(sslmode).lower()
    if mode in {"disable", "allow", "prefer"}:
        return {}
    return {"ssl": True}
