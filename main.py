"""Thin shell — real entry lives in :mod:`tui.cli`."""

from __future__ import annotations

from tui.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
