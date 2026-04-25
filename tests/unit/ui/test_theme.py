"""Theme default values — must match AGENTS.md §11."""

from __future__ import annotations

from ui.theme import DEFAULT, Theme


def test_default_theme_matches_agents_md_section_11() -> None:
    assert DEFAULT.role_user == "green"
    assert DEFAULT.role_assistant == "bright_cyan"
    assert DEFAULT.role_system == "grey50"


def test_theme_is_frozen() -> None:
    import dataclasses

    import pytest

    t = Theme()
    assert dataclasses.is_dataclass(t)
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.role_user = "red"  # type: ignore[misc]
