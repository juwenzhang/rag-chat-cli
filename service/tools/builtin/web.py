"""Small web tools for the agent loop.

These are intentionally provider-free: they use public HTTP endpoints and
return compact JSON payloads for the LLM, while attaching normalized web
sources in ``ToolResult.metadata`` for UI citations.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from service.tools import FunctionTool, Tool, ToolResult

__all__ = ["build_web_tools"]

_TIMEOUT = httpx.Timeout(12.0, connect=5.0)
_UA = "Mozilla/5.0 (compatible; rag-ai-cli/0.1; +https://localhost)"
_SEARCH_ENDPOINTS = (
    "https://html.duckduckgo.com/html/",
    "https://duckduckgo.com/html/",
)


class _SearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._href: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        d = dict(attrs)
        cls = d.get("class") or ""
        href = d.get("href")
        if href and "result__a" in cls:
            self._href = href
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._href is None:
            return
        title = " ".join("".join(self._buf).split())
        url = _clean_duckduckgo_url(self._href)
        if title and url:
            self.results.append({"title": title, "url": url})
        self._href = None
        self._buf = []


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.text: list[str] = []
        self._in_title = False
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        if self._in_title:
            self.title += cleaned
        elif self._skip == 0:
            self.text.append(cleaned)


def build_web_tools() -> list[Tool]:
    return [
        FunctionTool(
            name="web_search",
            description="Search the web for up-to-date information. Returns top result titles and URLs.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 8, "default": 5},
                },
                "required": ["query"],
            },
            fn=_web_search,
        ),
        FunctionTool(
            name="web_fetch",
            description="Fetch a web page by URL and extract readable text for citation.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "HTTP or HTTPS URL to fetch."},
                    "max_chars": {
                        "type": "integer",
                        "minimum": 500,
                        "maximum": 12000,
                        "default": 4000,
                    },
                },
                "required": ["url"],
            },
            fn=_web_fetch,
        ),
    ]


async def _web_search(args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query") or "").strip()
    if not query:
        return ToolResult(content="query is required", is_error=True)
    limit = _clamp_int(args.get("limit"), default=5, low=1, high=8)
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"},
            follow_redirects=True,
        ) as client:
            resp = await _fetch_search_results(client, query)
    except httpx.HTTPError as exc:
        return ToolResult(content=f"web_search failed: {type(exc).__name__}: {exc}", is_error=True)

    parser = _SearchParser()
    parser.feed(resp.text)
    results = parser.results[:limit]
    sources = [
        {"source_type": "web", "rank": i, "title": r["title"], "url": r["url"]}
        for i, r in enumerate(results, start=1)
    ]
    return ToolResult(
        content=json.dumps({"query": query, "results": results}, ensure_ascii=False),
        metadata={"sources": sources},
    )


async def _fetch_search_results(client: httpx.AsyncClient, query: str) -> httpx.Response:
    last_response: httpx.Response | None = None
    for endpoint in _SEARCH_ENDPOINTS:
        resp = await client.get(endpoint, params={"q": query})
        last_response = resp
        if resp.status_code < 400 and "result__a" in resp.text:
            return resp
    assert last_response is not None
    last_response.raise_for_status()
    return last_response


async def _web_fetch(args: dict[str, Any]) -> ToolResult:
    url = str(args.get("url") or "").strip()
    if not _is_http_url(url):
        return ToolResult(content="url must start with http:// or https://", is_error=True)
    max_chars = _clamp_int(args.get("max_chars"), default=4000, low=500, high=12000)
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, headers={"User-Agent": _UA}, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        return ToolResult(content=f"web_fetch failed: {type(exc).__name__}: {exc}", is_error=True)

    parser = _TextParser()
    parser.feed(resp.text)
    text = re.sub(r"\s+", " ", " ".join(parser.text)).strip()[:max_chars]
    title = parser.title.strip() or url
    source = {"source_type": "web", "rank": 1, "title": title, "url": str(resp.url), "quote": text}
    return ToolResult(
        content=json.dumps(
            {"url": str(resp.url), "title": title, "text": text}, ensure_ascii=False
        ),
        metadata={"sources": [source]},
    )


def _clean_duckduckgo_url(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(uddg)
    return href


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _clamp_int(value: object, *, default: int, low: int, high: int) -> int:
    n = default
    if isinstance(value, (str, bytes, bytearray, int, float)):
        try:
            n = int(value)
        except ValueError:
            n = default
    return max(low, min(high, n))
