"""Argparse-driven CLI entry (AGENTS.md §2, §15 P1).

``main.py`` is a thin shell around :func:`main`.
"""

from __future__ import annotations

import argparse
import asyncio

from app.chat_app import run_legacy_chat, run_tui_chat

__all__ = ["build_parser", "main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rag-chat")
    sub = parser.add_subparsers(dest="cmd", required=False)

    chat = sub.add_parser("chat", help="interactive chat (sequential REPL)")
    chat.add_argument(
        "--tui",
        action="store_true",
        help="(experimental) use the v1.3 full-screen three-pane TUI",
    )

    serve = sub.add_parser("serve", help="run FastAPI server (uvicorn)")
    serve.add_argument("--host", default=None, help="bind host (default: settings.app.host)")
    serve.add_argument(
        "--port", type=int, default=None, help="bind port (default: settings.app.port)"
    )
    serve.add_argument("--reload", action="store_true", help="autoreload on code change (dev)")
    serve.add_argument("--workers", type=int, default=1, help="uvicorn worker count")

    sub.add_parser("train", help="(stub) LoRA train")
    sub.add_parser("ingest", help="(stub) ingest knowledge")
    return parser


def _run_serve(ns: argparse.Namespace) -> int:
    """Boot uvicorn with the ``create_app`` factory."""
    import uvicorn

    from settings import settings

    host = ns.host or settings.app.host
    port = ns.port or settings.app.port

    uvicorn.run(
        "api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=bool(ns.reload),
        workers=int(ns.workers) if not ns.reload else 1,
        log_level=settings.app.log_level.lower(),
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    cmd = ns.cmd or "chat"
    if cmd == "chat":
        if getattr(ns, "tui", False):
            return asyncio.run(run_tui_chat())
        return asyncio.run(run_legacy_chat())
    if cmd == "serve":
        return _run_serve(ns)
    print(f"'{cmd}' not implemented yet")
    return 2
