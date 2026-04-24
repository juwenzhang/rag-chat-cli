"""CLI color palette (AGENTS.md §11).

Opencode-style: zero emojis, role-tagged colors, subtle dividers.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["DEFAULT", "Theme"]


@dataclass(frozen=True)
class Theme:
    """Immutable color palette for CLI rendering."""

    role_user: str = "green"
    role_assistant: str = "bright_cyan"
    role_system: str = "grey50"
    banner: str = "bold white"
    divider: str = "grey37"
    error: str = "red"
    ok: str = "green"


DEFAULT: Theme = Theme()
