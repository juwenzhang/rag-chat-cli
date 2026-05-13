"""Argparse-driven CLI entry.

``main.py`` is a thin shell around :func:`main`.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from app.chat_app import run_legacy_chat

__all__ = ["build_parser", "main"]

# Files we consider plain-text-ish. Extending this set is a deliberate act
# because binary formats (PDF, .docx) need a separate extractor pass that
# lives outside the ingestion pipeline.
TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {".txt", ".md", ".markdown", ".rst", ".text", ".py", ".json", ".yml", ".yaml", ".toml"}
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rag-chat")
    sub = parser.add_subparsers(dest="cmd", required=False)

    sub.add_parser("chat", help="interactive chat (sequential REPL)")

    serve = sub.add_parser("serve", help="run FastAPI server (uvicorn)")
    serve.add_argument("--host", default=None, help="bind host (default: settings.app.host)")
    serve.add_argument(
        "--port", type=int, default=None, help="bind port (default: settings.app.port)"
    )
    serve.add_argument("--reload", action="store_true", help="autoreload on code change (dev)")
    serve.add_argument("--workers", type=int, default=1, help="uvicorn worker count")

    sub.add_parser("train", help="(stub) LoRA train")

    ingest = sub.add_parser(
        "ingest",
        help="ingest text files/directories into the knowledge base",
    )
    ingest.add_argument("path", help="file or directory to ingest")
    ingest.add_argument(
        "--user-id",
        default=None,
        help="UUID of the owning user (default: shared/None — visible to everyone)",
    )
    ingest.add_argument(
        "--title", default=None, help="document title (default: filename stem)"
    )
    ingest.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="characters per chunk (default: pipeline default)",
    )
    ingest.add_argument(
        "--chunk-overlap",
        type=int,
        default=None,
        help="characters of overlap between adjacent chunks (default: pipeline default)",
    )
    ingest.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="when path is a directory, walk subdirectories",
    )
    ingest.add_argument(
        "--async",
        dest="run_async",
        action="store_true",
        help="enqueue each file to the Redis worker queue instead of ingesting inline",
    )

    worker = sub.add_parser("worker", help="run the background job worker (#23 P5.4)")
    worker.add_argument(
        "--queue",
        default=None,
        help="queue name (default: lhx-rag-cli:jobs)",
    )
    worker.add_argument(
        "--poll-timeout",
        type=float,
        default=5.0,
        help="seconds to block on BRPOP between polls",
    )
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


def _iter_target_files(root: Path, *, recursive: bool) -> list[Path]:
    """Return the list of files this ``ingest`` invocation will process.

    Files are filtered against :data:`TEXT_EXTENSIONS` so a typo
    pointing at a media folder doesn't dump GB into the embedder.
    """
    if root.is_file():
        return [root]
    if not root.is_dir():
        raise FileNotFoundError(f"path not found: {root}")
    glob = root.rglob("*") if recursive else root.glob("*")
    return sorted(
        p
        for p in glob
        if p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS
    )


async def _run_ingest_async(ns: argparse.Namespace) -> int:
    """Async body of :func:`_run_ingest`. Returns the CLI exit code."""
    from core.knowledge import DocumentIngestor
    from core.llm.ollama import OllamaClient
    from db.session import current_session_factory, init_engine
    from settings import settings

    # Synchronous file I/O is fine here: this is a one-shot CLI command,
    # not a server hot path. ASYNC240 would push us toward anyio/trio.path
    # which is overkill for a script that reads each file once.
    root = Path(ns.path).expanduser()  # noqa: ASYNC240
    try:
        files = _iter_target_files(root, recursive=bool(ns.recursive))
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not files:
        print(
            f"no text files to ingest under {root} "
            f"(supported extensions: {', '.join(sorted(TEXT_EXTENSIONS))})",
            file=sys.stderr,
        )
        return 2

    user_id: uuid.UUID | None = None
    if ns.user_id is not None:
        try:
            user_id = uuid.UUID(ns.user_id)
        except ValueError:
            print(f"invalid --user-id: {ns.user_id!r}", file=sys.stderr)
            return 2

    # ``--async`` path: enqueue jobs to the Redis worker queue and return.
    # The worker (``main worker``) consumes them out-of-band.
    if getattr(ns, "run_async", False):
        from core.workers import JobSpec, RedisJobQueue

        queue = RedisJobQueue.from_url()
        try:
            for f in files:
                await queue.enqueue(
                    JobSpec(
                        kind="ingest_document",
                        payload={
                            "path": str(f.resolve()),
                            "user_id": str(user_id) if user_id is not None else None,
                            "title": ns.title,
                        },
                    )
                )
                print(f"  ↑ queued {f}")
        finally:
            await queue.aclose()
        print(f"queued {len(files)} ingest job(s); run `main worker` to process")
        return 0

    init_engine()
    sf = current_session_factory()
    llm = OllamaClient.from_settings(settings)

    kwargs: dict[str, int] = {}
    if ns.chunk_size is not None:
        kwargs["chunk_size"] = ns.chunk_size
    if ns.chunk_overlap is not None:
        kwargs["chunk_overlap"] = ns.chunk_overlap

    ingestor = DocumentIngestor(
        session_factory=sf,
        llm=llm,
        user_id=user_id,
        embed_model=settings.ollama.embed_model,
        **kwargs,
    )

    total_chunks = 0
    failed = 0
    try:
        for f in files:
            try:
                result = await ingestor.ingest_file(f, title=ns.title)
            except Exception as exc:
                print(f"  ✗ {f} — {type(exc).__name__}: {exc}", file=sys.stderr)
                failed += 1
                continue
            print(
                f"  ✓ {f}  →  doc={result.document_id}  "
                f"chunks={result.chunk_count}  chars={result.char_count}"
            )
            total_chunks += result.chunk_count
    finally:
        await llm.aclose()

    print(
        f"ingest finished: {len(files) - failed}/{len(files)} files OK, "
        f"{total_chunks} chunks written"
        + (f", {failed} failed" if failed else "")
    )
    return 0 if failed == 0 else 1


def _run_ingest(ns: argparse.Namespace) -> int:
    return asyncio.run(_run_ingest_async(ns))


def _run_worker(ns: argparse.Namespace) -> int:
    """Run the background job worker (``main worker``).

    Registers known job kinds (currently just ``ingest_document``) and
    runs until SIGINT. The handler is wired here rather than in
    :mod:`core.workers` so the worker module stays free of `app/` deps.
    """
    import contextlib
    import signal

    from core.knowledge import DocumentIngestor
    from core.llm.ollama import OllamaClient
    from core.workers import JobSpec, RedisJobQueue, Worker
    from db.session import current_session_factory, init_engine
    from settings import settings

    async def _handle_ingest(job: JobSpec) -> None:
        # Re-create per-job so a torn DB / LLM connection doesn't poison
        # subsequent jobs. Cheap by design.
        path = job.payload.get("path")
        user_id_raw = job.payload.get("user_id")
        if not isinstance(path, str):
            raise ValueError(f"ingest_document job missing 'path': {job!r}")
        user_id = uuid.UUID(user_id_raw) if isinstance(user_id_raw, str) else None
        init_engine()
        sf = current_session_factory()
        llm = OllamaClient.from_settings(settings)
        try:
            ingestor = DocumentIngestor(
                session_factory=sf,
                llm=llm,
                user_id=user_id,
                embed_model=settings.ollama.embed_model,
            )
            result = await ingestor.ingest_file(path, title=job.payload.get("title"))
            print(
                f"[worker] ingested {path} → doc={result.document_id} "
                f"chunks={result.chunk_count}"
            )
        finally:
            await llm.aclose()

    async def _run() -> None:
        from core.workers.queue import DEFAULT_QUEUE_NAME

        queue = RedisJobQueue.from_url(name=ns.queue or DEFAULT_QUEUE_NAME)
        worker = Worker(queue=queue, poll_timeout_s=float(ns.poll_timeout))
        worker.register("ingest_document", _handle_ingest)

        # Wire signals → cancel the run_forever task.
        loop = asyncio.get_running_loop()
        task = asyncio.create_task(worker.run_forever())
        for sig in (signal.SIGINT, signal.SIGTERM):
            # Windows / non-main-thread can't install a signal handler — fall back to KeyboardInterrupt.
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, task.cancel)
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            await queue.aclose()

    asyncio.run(_run())
    return 0


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    cmd = ns.cmd or "chat"
    if cmd == "chat":
        return asyncio.run(run_legacy_chat())
    if cmd == "serve":
        return _run_serve(ns)
    if cmd == "ingest":
        return _run_ingest(ns)
    if cmd == "worker":
        return _run_worker(ns)
    print(f"'{cmd}' not implemented yet")
    return 2
