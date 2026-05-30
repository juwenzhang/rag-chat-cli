"""Read-only codebase tools for the agent loop."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from service.tools import FunctionTool, Tool, ToolResult

__all__ = ["build_codebase_tools"]

_MAX_FILE_BYTES = 80_000
_DEFAULT_GLOBS = {"*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.md", "*.toml", "*.yaml", "*.yml"}
_SKIP_DIRS = {".git", ".next", "node_modules", "__pycache__", ".venv", "dist", "build"}


def build_codebase_tools(root: str | Path | None = None) -> list[Tool]:
    base = Path(root or Path.cwd()).resolve()
    return [
        FunctionTool(
            name="code_search",
            description="Search this project for a literal or regex pattern and return file/line matches.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Literal text or regex to search for.",
                    },
                    "regex": {"type": "boolean", "default": False},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
                },
                "required": ["query"],
            },
            fn=lambda args: _code_search(base, args),
        ),
        FunctionTool(
            name="read_project_file",
            description="Read a project file by relative path. Use after code_search to inspect context.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path inside the project."},
                    "start_line": {"type": "integer", "minimum": 1, "default": 1},
                    "max_lines": {"type": "integer", "minimum": 1, "maximum": 240, "default": 120},
                },
                "required": ["path"],
            },
            fn=lambda args: _read_project_file(base, args),
        ),
    ]


async def _code_search(root: Path, args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query") or "").strip()
    if not query:
        return ToolResult(content="query is required", is_error=True)
    limit = _clamp_int(args.get("limit"), default=20, low=1, high=50)
    use_regex = bool(args.get("regex"))
    try:
        pattern = re.compile(query if use_regex else re.escape(query), re.IGNORECASE)
    except re.error as exc:
        return ToolResult(content=f"invalid regex: {exc}", is_error=True)

    matches: list[dict[str, object]] = []
    for path in _iter_files(root):
        if len(matches) >= limit:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                rel = str(path.relative_to(root))
                matches.append({"path": rel, "line": lineno, "text": line.strip()[:240]})
                if len(matches) >= limit:
                    break

    sources = [
        {
            "source_type": "tool",
            "rank": i,
            "title": f"{m['path']}:{m['line']}",
            "quote": str(m["text"]),
            "source": "code_search",
        }
        for i, m in enumerate(matches, start=1)
    ]
    return ToolResult(
        content=json.dumps({"query": query, "matches": matches}, ensure_ascii=False),
        metadata={"sources": sources},
    )


async def _read_project_file(root: Path, args: dict[str, Any]) -> ToolResult:
    rel = str(args.get("path") or "").strip()
    if not rel:
        return ToolResult(content="path is required", is_error=True)
    try:
        path = (root / rel).resolve()
        path.relative_to(root)
    except ValueError:
        return ToolResult(content="path must stay inside the project", is_error=True)
    if not path.is_file():
        return ToolResult(content="file not found", is_error=True)
    if path.stat().st_size > _MAX_FILE_BYTES:
        return ToolResult(content=f"file too large ({path.stat().st_size} bytes)", is_error=True)

    start = _clamp_int(args.get("start_line"), default=1, low=1, high=1_000_000)
    max_lines = _clamp_int(args.get("max_lines"), default=120, low=1, high=240)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return ToolResult(content=f"read failed: {exc}", is_error=True)
    end = min(len(lines), start + max_lines - 1)
    selected = lines[start - 1 : end]
    numbered = "\n".join(f"{i}: {line}" for i, line in enumerate(selected, start=start))
    title = f"{rel}:{start}-{end}"
    return ToolResult(
        content=json.dumps(
            {"path": rel, "start_line": start, "end_line": end, "content": numbered},
            ensure_ascii=False,
        ),
        metadata={
            "sources": [
                {
                    "source_type": "tool",
                    "rank": 1,
                    "title": title,
                    "quote": numbered[:4000],
                    "source": "read_project_file",
                }
            ]
        },
    )


def _iter_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and any(path.match(glob) for glob in _DEFAULT_GLOBS):
            yield path


def _clamp_int(value: object, *, default: int, low: int, high: int) -> int:
    n = default
    if isinstance(value, (str, bytes, bytearray, int, float)):
        try:
            n = int(value)
        except ValueError:
            n = default
    return max(low, min(high, n))
