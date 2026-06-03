"""Factory for per-request built-in tool registries."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from service.tools.builtin import build_codebase_tools, build_web_tools
from service.tools.registry import ToolRegistry

__all__ = ["build_builtin_tool_registry"]


def build_builtin_tool_registry(
    *,
    project_root: str | Path | None = None,
    ollama_api_key: str | Callable[[], str | None] | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in [
        *build_web_tools(ollama_api_key=ollama_api_key),
        *build_codebase_tools(project_root),
    ]:
        registry.register(tool)
    return registry
