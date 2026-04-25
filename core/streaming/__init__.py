"""Core-layer streaming primitives (AGENTS.md §3).

Lives under ``core/`` instead of ``api/`` so :class:`ChatService` can depend
on it without violating the "core must not import api" red line. API-layer
routers re-use the same types via plain import.
"""

from __future__ import annotations

__all__: list[str] = []
