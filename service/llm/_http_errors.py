"""Shared HTTP → LLMError classifier for Ollama / OpenAI clients.

Centralises detection of common upstream conditions (rate limit, paywall,
auth, 404, generic 5xx / HTML) so both adapters surface the same
:class:`LLMError` subclasses with consistent ``code``, ``upstream_status``,
``upstream_url`` and ``retry_after`` fields.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from service.llm.client import (
    LLMAuthError,
    LLMError,
    LLMModelNotFoundError,
    LLMRateLimitError,
    LLMSubscriptionRequiredError,
    LLMUpstreamUnavailableError,
)

__all__ = ["classify_http_error"]


_OLLAMA_UPGRADE_RE = re.compile(r"https?://ollama\.com/upgrade[^\s\")]*", re.IGNORECASE)
_SUBSCRIPTION_HINT_RE = re.compile(r"requires a subscription", re.IGNORECASE)


def classify_http_error(
    *,
    provider: str,
    status: int,
    headers: Mapping[str, str] | None,
    body: bytes | str,
) -> LLMError:
    """Build the most specific :class:`LLMError` for a non-2xx HTTP response.

    Never echoes raw HTML to callers — bodies that look like HTML are
    summarised as "<HTML error page>" so logs and SSE frames stay clean.
    """

    text = _decode(body)
    is_html = _looks_like_html(text)
    snippet = "<HTML error page>" if is_html else text[:200]
    retry_after = _parse_retry_after(headers)
    upgrade_url = _extract_upgrade_url(text)

    # Subscription paywall takes precedence over a generic 4xx, since the
    # status alone (often 402 / 403) is ambiguous without the body hint.
    if upgrade_url or (_SUBSCRIPTION_HINT_RE.search(text) and status in (402, 403)):
        return LLMSubscriptionRequiredError(
            f"{provider} model requires a paid subscription",
            upstream_status=status,
            upstream_url=upgrade_url or "https://ollama.com/upgrade",
            retry_after=retry_after,
        )

    if status == 429:
        return LLMRateLimitError(
            f"{provider} upstream rate-limited",
            upstream_status=status,
            retry_after=retry_after,
        )

    if status in (401, 403):
        return LLMAuthError(
            f"{provider} rejected the API key (HTTP {status})",
            upstream_status=status,
        )

    if status == 404 and not is_html and "not found" in text.lower():
        return LLMModelNotFoundError(
            f"{provider} model not found",
            upstream_status=status,
        )

    if status >= 500 or is_html:
        return LLMUpstreamUnavailableError(
            f"{provider} upstream unavailable: HTTP {status} {snippet!r}",
            upstream_status=status,
            retry_after=retry_after,
        )

    return LLMError(
        f"{provider} request failed: HTTP {status} {snippet!r}",
        upstream_status=status,
        retry_after=retry_after,
    )


def _decode(body: bytes | str) -> str:
    if isinstance(body, str):
        return body
    return body.decode("utf-8", errors="replace")


def _looks_like_html(text: str) -> bool:
    head = text.lstrip()[:64].lower()
    return head.startswith(("<!doctype", "<html", "<!--"))


def _parse_retry_after(headers: Mapping[str, str] | None) -> int | None:
    if not headers:
        return None
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0, int(float(raw)))
    except (TypeError, ValueError):
        return None


def _extract_upgrade_url(text: str) -> str | None:
    m = _OLLAMA_UPGRADE_RE.search(text)
    return m.group(0) if m else None
