"""Backend service layer.

This package owns business services, provider/runtime integration, persistence
infrastructure, background workers, and domain adapters. Entry layers such as
``api/`` may depend on ``service/``; ``service/`` must not depend on entry layers.

This ``__init__`` deliberately exposes nothing: callers should import from
specific sub-packages such as ``service.llm``, ``service.memory``,
``service.knowledge`` or the chat orchestrator.
"""

from __future__ import annotations

__all__: list[str] = []
