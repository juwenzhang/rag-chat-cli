"""Liveness / readiness endpoints.

``/health`` is the one route the access log middleware explicitly skips,
so this module stays deliberately minimal.
"""

from __future__ import annotations

from fastapi import APIRouter

__all__ = ["router"]

router = APIRouter(tags=["meta"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    """Return ``{"status": "ok"}`` if the process is alive."""
    return {"status": "ok"}
