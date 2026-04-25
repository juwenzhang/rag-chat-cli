"""Thin shell — real entry lives in :mod:`app.cli`."""

from __future__ import annotations

from app.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
