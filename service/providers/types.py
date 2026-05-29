"""Provider shared type aliases and constants."""

from __future__ import annotations

from typing import Literal

__all__ = ["SUPPORTED_TYPES", "ProviderType"]

ProviderType = Literal["ollama", "openai"]
SUPPORTED_TYPES: frozenset[str] = frozenset({"ollama", "openai"})
