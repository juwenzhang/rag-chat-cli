"""Run repository quality gates for backend and frontend."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Sequence

BACKEND_CHECKS: tuple[tuple[str, ...], ...] = (
    ("uv", "run", "ruff", "check", "."),
    ("uv", "run", "ruff", "format", "--check", "."),
    ("uv", "run", "mypy", "api", "service", "settings.py", "scripts"),
    (
        "python3",
        "-m",
        "compileall",
        "-q",
        "api",
        "service",
        "settings.py",
        "scripts",
        "alembic",
    ),
)

FRONTEND_CHECKS: tuple[tuple[str, ...], ...] = (
    ("pnpm", "--dir", "websites", "lint"),
    ("pnpm", "--dir", "websites", "format:check"),
    ("pnpm", "--dir", "websites", "typecheck"),
)


def run_commands(commands: Sequence[Sequence[str]]) -> None:
    for command in commands:
        print("$ " + " ".join(command), flush=True)
        subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run project quality gates")
    parser.add_argument("target", choices=("backend", "frontend", "all"), nargs="?", default="all")
    args = parser.parse_args()

    if args.target in {"backend", "all"}:
        run_commands(BACKEND_CHECKS)
    if args.target in {"frontend", "all"}:
        run_commands(FRONTEND_CHECKS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
