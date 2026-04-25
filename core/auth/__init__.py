"""Authentication domain.

Keeps the public surface empty on purpose — callers must import from
submodules (``core.auth.service``, ``core.auth.tokens``…). See AGENTS.md §3
for the re-export rule.
"""

from __future__ import annotations

__all__: list[str] = []
