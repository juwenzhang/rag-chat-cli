"""CLI boot smoke test — ``python main.py --help`` must exit cleanly."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_main_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, "main.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "chat" in result.stdout


def test_stub_subcommand_prints_not_implemented() -> None:
    """``train`` still has no implementation; exit code must be 2."""
    result = subprocess.run(
        [sys.executable, "main.py", "train"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "not implemented yet" in result.stdout


def test_serve_help_exits_zero() -> None:
    """``serve --help`` lists the flags added in P6."""
    result = subprocess.run(
        [sys.executable, "main.py", "serve", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "--host" in result.stdout
    assert "--port" in result.stdout
