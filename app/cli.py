"""Argparse-driven CLI entry (AGENTS.md §2, §15 P1).

``main.py`` is a thin shell around :func:`main`.
"""

from __future__ import annotations

import argparse
import asyncio

from app.chat_app import run_chat

__all__ = ["build_parser", "main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rag-chat")
    sub = parser.add_subparsers(dest="cmd", required=False)
    sub.add_parser("chat", help="interactive chat")
    sub.add_parser("serve", help="(stub) run FastAPI server")
    sub.add_parser("train", help="(stub) LoRA train")
    sub.add_parser("ingest", help="(stub) ingest knowledge")
    return parser


def _model_label() -> str:
    """Best-effort model label for the banner.

    Reads from :mod:`settings`; degrades to a placeholder if settings fail
    to load (e.g. no ``.env`` on first boot).
    """

    try:
        from settings import settings  # local import keeps CLI cold-path light

        return settings.ollama.chat_model
    except Exception:
        return "echo-provider"


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    cmd = ns.cmd or "chat"
    if cmd == "chat":
        return asyncio.run(run_chat(model_label=_model_label()))
    print(f"'{cmd}' not implemented yet")
    return 2
