"""HTTP / WebSocket layer (AGENTS.md §2, §3).

Only thin FastAPI wiring lives here — business logic belongs in ``core/``.
P6 ``add-jwt-auth`` only lands the ``schemas/`` and ``deps.py`` building
blocks; actual routers are the responsibility of
``add-fastapi-rest-api``.
"""

from __future__ import annotations

__all__: list[str] = []
