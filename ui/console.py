"""Rich Console factory + decoration helpers (AGENTS.md §11).

Kept minimal — purely presentational, no business logic.
"""

from __future__ import annotations

from rich.console import Console

from ui.theme import DEFAULT, Theme

__all__ = ["make_console", "print_banner", "print_divider"]


def make_console() -> Console:
    """Build a Console with emoji auto-replacement disabled.

    Opencode-style CLI avoids emoji; we keep ``:foo:`` literal strings literal.
    """

    return Console(emoji=False, highlight=False, soft_wrap=False)


def print_banner(console: Console, model: str, theme: Theme = DEFAULT) -> None:
    """Print the single-line ready banner: ``rag-chat · <model> · ready``."""

    console.print(f"[{theme.banner}]rag-chat · {model} · ready[/]")


def print_divider(console: Console, theme: Theme = DEFAULT) -> None:
    """Print a subtle horizontal divider (full console width)."""

    width = console.size.width
    console.print(f"[{theme.divider}]{'─' * width}[/]")
