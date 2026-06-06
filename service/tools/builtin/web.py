"""Small web tools for the agent loop.

When an Ollama API key is available, web search/fetch use Ollama's official
web endpoints first. They fall back to public HTTP endpoints so local/dev
setups without a key still have a best-effort path. Results are returned as
compact JSON payloads for the LLM, with normalized web sources attached in
``ToolResult.metadata`` for UI citations.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from service.tools import FunctionTool, Tool, ToolResult

__all__ = ["build_web_tools"]

_TIMEOUT = httpx.Timeout(12.0, connect=5.0)
_UA = "Mozilla/5.0 (compatible; rag-ai-cli/0.1; +https://localhost)"
_OLLAMA_WEB_SEARCH_URL = "https://ollama.com/api/web_search"
_OLLAMA_WEB_FETCH_URL = "https://ollama.com/api/web_fetch"
_SEARCH_ENDPOINTS = (
    "https://html.duckduckgo.com/html/",
    "https://duckduckgo.com/html/",
    "https://lite.duckduckgo.com/lite/",
)
_MAX_SEARCH_QUERY_CHARS = 240
_MAX_SEARCH_RESULTS = 5
_MAX_SEARCH_SNIPPET_CHARS = 700
_MAX_SEARCH_TOTAL_SNIPPET_CHARS = 3_000
_MAX_FETCH_CHARS = 6_000


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
        if href and ("result__a" in cls or "result-link" in cls):
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


_WEB_SEARCH_DESCRIPTION = """Search the web for up-to-date information.

WHEN to use:
  - The question requires recent / time-sensitive information.
  - You need sources you can cite ([1], [2], …).
  - You're unsure about a specific fact and want verification.
  - Local knowledge-base retrieval came back empty or weak.

STRATEGY (most users skip step 2 — don't):
  1. Issue an initial broad search.
  2. If results look weak / off-topic / one-sided, run a SECOND search
     with reformulated keywords (synonyms, narrower scope, different
     language, or the opposite angle for comparison questions).
  3. Pick 2–3 of the most relevant URLs and use ``web_fetch`` on each
     to read the actual content. Snippets alone are rarely enough.

QUERY hygiene:
  - Keep queries focused (≤ 10 words). Long natural-language queries
    match poorly on most search backends.
  - Don't repeat the user's full question verbatim — extract the key
    entities + intent.

Returns compact result titles, URLs and short snippets in JSON. Plan
to chain at least one ``web_fetch`` after a successful search."""

_WEB_FETCH_DESCRIPTION = """Fetch a web page and extract readable text for citation.

WHEN to use:
  - After ``web_search`` returned promising URLs.
  - The user gave you a URL directly.
  - You need the FULL article body, not just a snippet, to ground a
    factual claim.

STRATEGY:
  - For non-trivial questions, fetch 2–3 URLs from the search results
    rather than just one. A single source is often biased, outdated,
    or incomplete; triangulating across multiple sources is what
    separates a confident answer from a guess.
  - Prefer primary sources (official docs, the project's own blog, a
    news outlet's article) over aggregators (forum index, tag pages,
    listicles).
  - If a fetched page is gated / 404 / mostly nav-chrome, don't give
    up — fetch the next-best URL from the same search.

Returns the page title and main text up to ``max_chars`` characters."""


def build_web_tools(
    *,
    ollama_api_key: str | Callable[[], str | None] | None = None,
) -> list[Tool]:
    return [
        FunctionTool(
            name="web_search",
            description=_WEB_SEARCH_DESCRIPTION,
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5, "default": 5},
                },
                "required": ["query"],
            },
            fn=lambda args: _web_search(args, ollama_api_key=_resolve_api_key(ollama_api_key)),
        ),
        FunctionTool(
            name="web_fetch",
            description=_WEB_FETCH_DESCRIPTION,
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "HTTP or HTTPS URL to fetch."},
                    "max_chars": {
                        "type": "integer",
                        "minimum": 500,
                        "maximum": 6000,
                        "default": 4000,
                    },
                },
                "required": ["url"],
            },
            fn=lambda args: _web_fetch(args, ollama_api_key=_resolve_api_key(ollama_api_key)),
        ),
    ]


def _resolve_api_key(value: str | Callable[[], str | None] | None) -> str | None:
    return value() if callable(value) else value


async def _web_search(args: dict[str, Any], *, ollama_api_key: str | None = None) -> ToolResult:
    raw_query = str(args.get("query") or "").strip()
    query = _compact_query(raw_query)
    if not query:
        return ToolResult(content="query is required", is_error=True)
    limit = _clamp_int(args.get("limit"), default=5, low=1, high=_MAX_SEARCH_RESULTS)

    official_error: str | None = None
    if ollama_api_key:
        try:
            return await _ollama_web_search(query, limit=limit, api_key=ollama_api_key)
        except (httpx.HTTPError, ValueError) as exc:
            official_error = f"ollama web_search: {type(exc).__name__}: {exc}"

    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"},
            follow_redirects=True,
        ) as client:
            resp = await _fetch_search_results(client, query)
    except httpx.HTTPError as exc:
        warning = f"duckduckgo web_search: {type(exc).__name__}: {exc}"
        if official_error:
            warning = f"{official_error}; {warning}"
        return ToolResult(
            content=json.dumps(
                {
                    "query": query,
                    "results": [],
                    "warning": f"web_search unavailable: {warning}",
                },
                ensure_ascii=False,
            ),
            is_error=True,
            metadata={"sources": []},
        )

    parser = _SearchParser()
    parser.feed(resp.text)
    results = _clip_search_results(parser.results[:limit])
    sources = _sources_from_search_results(results)
    payload: dict[str, Any] = {"query": query, "results": results, "provider": "duckduckgo"}
    if official_error:
        payload["warning"] = f"official search unavailable; used fallback: {official_error}"
    return ToolResult(
        content=json.dumps(payload, ensure_ascii=False),
        metadata={"sources": sources},
    )


async def _ollama_web_search(query: str, *, limit: int, api_key: str) -> ToolResult:
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_ollama_headers(api_key)) as client:
        resp = await client.post(
            _OLLAMA_WEB_SEARCH_URL,
            json={"query": query, "max_results": limit},
        )
        resp.raise_for_status()
        data = resp.json()

    results = _clip_search_results(_normalize_ollama_search_results(data, limit=limit))
    return ToolResult(
        content=json.dumps(
            {"query": query, "results": results, "provider": "ollama"},
            ensure_ascii=False,
        ),
        metadata={"sources": _sources_from_search_results(results)},
    )


def _normalize_ollama_search_results(data: Any, *, limit: int) -> list[dict[str, str]]:
    raw_results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(raw_results, list):
        return []

    results: list[dict[str, str]] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        title = _compact_text(str(item.get("title") or url).strip(), max_chars=240)
        quote = _compact_text(
            str(item.get("content") or item.get("snippet") or item.get("text") or "").strip(),
            max_chars=_MAX_SEARCH_SNIPPET_CHARS,
        )
        result = {"title": title, "url": url}
        if quote:
            result["content"] = quote
        results.append(result)
        if len(results) >= limit:
            break
    return results


def _clip_search_results(results: list[dict[str, str]]) -> list[dict[str, str]]:
    clipped: list[dict[str, str]] = []
    remaining_snippet_chars = _MAX_SEARCH_TOTAL_SNIPPET_CHARS
    for result in results[:_MAX_SEARCH_RESULTS]:
        item = {
            "title": _compact_text(result.get("title", ""), max_chars=240),
            "url": result.get("url", ""),
        }
        content = result.get("content")
        if content and remaining_snippet_chars > 0:
            snippet = _compact_text(
                content,
                max_chars=min(_MAX_SEARCH_SNIPPET_CHARS, remaining_snippet_chars),
            )
            if snippet:
                item["content"] = snippet
                remaining_snippet_chars -= len(snippet)
        clipped.append(item)
    return clipped


def _sources_from_search_results(results: list[dict[str, str]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for i, result in enumerate(results, start=1):
        source: dict[str, Any] = {
            "source_type": "web",
            "rank": i,
            "title": result["title"],
            "url": result["url"],
        }
        quote = result.get("content")
        if quote:
            source["quote"] = quote
        sources.append(source)
    return sources


async def _fetch_search_results(client: httpx.AsyncClient, query: str) -> httpx.Response:
    last_success: httpx.Response | None = None
    last_response: httpx.Response | None = None
    errors: list[str] = []
    for endpoint in _SEARCH_ENDPOINTS:
        try:
            resp = await client.get(endpoint, params={"q": query})
        except httpx.HTTPError as exc:
            errors.append(f"{endpoint}: {type(exc).__name__}: {exc}")
            continue
        last_response = resp
        if resp.status_code >= 400:
            errors.append(f"{endpoint}: HTTP {resp.status_code}")
            continue
        last_success = resp
        if _has_search_result_marker(resp.text):
            return resp
    if last_success is not None:
        return last_success
    if last_response is not None:
        last_response.raise_for_status()
        return last_response
    raise httpx.HTTPError("; ".join(errors) or "no search endpoints configured")


def _has_search_result_marker(html: str) -> bool:
    return "result__a" in html or "result-link" in html


async def _web_fetch(args: dict[str, Any], *, ollama_api_key: str | None = None) -> ToolResult:
    url = str(args.get("url") or "").strip()
    if not _is_http_url(url):
        return ToolResult(content="url must start with http:// or https://", is_error=True)
    max_chars = _clamp_int(args.get("max_chars"), default=4000, low=500, high=_MAX_FETCH_CHARS)

    official_error: str | None = None
    if ollama_api_key:
        try:
            return await _ollama_web_fetch(url, max_chars=max_chars, api_key=ollama_api_key)
        except (httpx.HTTPError, ValueError) as exc:
            official_error = f"ollama web_fetch: {type(exc).__name__}: {exc}"

    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, headers={"User-Agent": _UA}, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        message = f"direct web_fetch: {type(exc).__name__}: {exc}"
        if official_error:
            message = f"{official_error}; {message}"
        return ToolResult(content=f"web_fetch failed: {message}", is_error=True)

    parser = _TextParser()
    parser.feed(resp.text)
    text = _compact_text(" ".join(parser.text), max_chars=max_chars)
    title = _compact_text(parser.title.strip() or url, max_chars=240)
    source = {"source_type": "web", "rank": 1, "title": title, "url": str(resp.url), "quote": text}
    payload: dict[str, Any] = {
        "url": str(resp.url),
        "title": title,
        "text": text,
        "provider": "direct",
    }
    if official_error:
        payload["warning"] = f"official fetch unavailable; used fallback: {official_error}"
    return ToolResult(
        content=json.dumps(payload, ensure_ascii=False),
        metadata={"sources": [source]},
    )


async def _ollama_web_fetch(url: str, *, max_chars: int, api_key: str) -> ToolResult:
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_ollama_headers(api_key)) as client:
        resp = await client.post(_OLLAMA_WEB_FETCH_URL, json={"url": url})
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, dict):
        raise ValueError("malformed Ollama web_fetch response")
    final_url = str(data.get("url") or url).strip()
    title = str(data.get("title") or final_url).strip()
    text = str(data.get("content") or data.get("text") or "").strip()[:max_chars]
    source = {"source_type": "web", "rank": 1, "title": title, "url": final_url, "quote": text}
    return ToolResult(
        content=json.dumps(
            {"url": final_url, "title": title, "text": text, "provider": "ollama"},
            ensure_ascii=False,
        ),
        metadata={"sources": [source]},
    )


def _ollama_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


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


def _compact_query(query: str) -> str:
    return _compact_text(query, max_chars=_MAX_SEARCH_QUERY_CHARS)


def _compact_text(text: str, *, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max(0, max_chars - 1)].rstrip() + "…"


def _clamp_int(value: object, *, default: int, low: int, high: int) -> int:
    n = default
    if isinstance(value, (str, bytes, bytearray, int, float)):
        try:
            n = int(value)
        except ValueError:
            n = default
    return max(low, min(high, n))
