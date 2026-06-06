"""HF Space keep-alive worker.

Two responsibilities, one process:

1. **Background ping loop** — every ``PING_INTERVAL_S`` seconds, GET
   each URL in ``TARGETS``. This is what keeps the *other* HF Spaces
   awake (their sleep lifecycle is gated on "received traffic").

2. **Tiny HTTP server on $PORT** — accepts external pings against
   ``/`` and ``/health``. This is what keeps *this* Space awake
   under HF's "received traffic" rule even if the loop somehow
   stalls; the GitHub Actions cron in the main repo pings this
   endpoint as the redundant "A" leg.

The main process is ``asyncio.run(ping_loop())`` so it never exits;
HF's other sleep heuristic ("idle process") therefore can't fire either.

Targets are configured via the ``TARGETS`` env var (newline-separated
URLs). Defaults match the rag-chat-cli stack.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("keepalive")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_TARGETS = """
https://luhanxin-rag-chat-backend.hf.space/health
https://luhanxin-hf-ollama-service.hf.space/api/tags
https://luhanxin-hf-luhanxin-minio.hf.space/minio/health/live
""".strip()

TARGETS = [
    line.strip()
    for line in os.getenv("TARGETS", DEFAULT_TARGETS).splitlines()
    if line.strip() and not line.strip().startswith("#")
]
# 600 s = 10 min. With the A leg also pinging at */10 we land at
# ~12 hits/hour per target, comfortably below HF's free-tier rate-limit
# threshold for "/" paths.
PING_INTERVAL_S = int(os.getenv("PING_INTERVAL_S", "600"))
PING_TIMEOUT_S = float(os.getenv("PING_TIMEOUT_S", "30"))
PORT = int(os.getenv("PORT", "7860"))

# Browser-shaped User-Agent — httpx default ('python-httpx/0.x') is the
# fastest way to get rate-limited by HF's edge. Real Firefox UA stays
# under the heuristic radar.
_HTTP_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"),
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


# ---------------------------------------------------------------------------
# Background ping loop
# ---------------------------------------------------------------------------
async def ping_once(client: httpx.AsyncClient, url: str) -> None:
    try:
        r = await client.get(url, timeout=PING_TIMEOUT_S)
        log.info("ping %s -> %d", url, r.status_code)
    except Exception as exc:  # broad catch: best-effort, never rethrow
        log.warning("ping %s failed: %s", url, exc)


# An Event we never set — used as a cancellable infinite sleeper. Lets
# ruff's ASYNC110 stay green without sacrificing readability.
_never = asyncio.Event()


async def ping_loop() -> None:
    if not TARGETS:
        log.warning("no TARGETS configured; idling")
        await _never.wait()
        return

    log.info("ping loop: %d target(s), interval=%ds", len(TARGETS), PING_INTERVAL_S)
    async with httpx.AsyncClient(
        follow_redirects=True,
        headers=_HTTP_HEADERS,
    ) as client:
        # First cycle runs immediately so we don't have to wait
        # PING_INTERVAL_S after a fresh container start.
        while not _never.is_set():
            await asyncio.gather(*(ping_once(client, u) for u in TARGETS))
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(_never.wait(), timeout=PING_INTERVAL_S)


# ---------------------------------------------------------------------------
# HTTP probe server (so external cron can ping us back)
# ---------------------------------------------------------------------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = (
            f'{{"ok":true,"now":"{datetime.now(timezone.utc).isoformat()}",'
            f'"targets":{len(TARGETS)},"interval_s":{PING_INTERVAL_S}}}'
        ).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # Suppress default per-request access log; we already log ping cycles.
        return


def serve_http() -> None:
    log.info("http listening on :%d", PORT)
    # 0.0.0.0 is required by HF Space — the platform routes external
    # traffic into the container via this bind address.
    ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()  # noqa: S104


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    Thread(target=serve_http, daemon=True).start()
    asyncio.run(ping_loop())


if __name__ == "__main__":
    main()
