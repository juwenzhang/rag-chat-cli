"""Business-domain layer.

AGENTS.md §2 places pure business logic here. AGENTS.md §3 forbids ``core/``
from importing ``api/``, ``ui/``, ``workers/`` or concrete ORM models — only
``db.session`` style abstractions are allowed.

This ``__init__`` deliberately exposes nothing: callers must import from
sub-packages (``core.llm``, ``core.memory``, ``core.knowledge``) or the
orchestrator (``core.chat_service``). Keeping the surface empty prevents the
"re-export everything" anti-pattern the earlier ``utils/`` package suffered.
"""

from __future__ import annotations

__all__: list[str] = []
