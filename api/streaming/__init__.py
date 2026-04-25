"""Shared streaming primitives (AGENTS.md §5.3).

Re-exports are intentionally empty — the SSE router, WebSocket router, and
the CLI all import from the concrete submodules directly. That keeps the
import graph easy to reason about.
"""

from __future__ import annotations

__all__: list[str] = []
