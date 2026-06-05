"""Shared HTTP plumbing for :class:`OllamaClient` and :class:`OpenAIClient`.

Both backends speak HTTP-over-``httpx.AsyncClient`` and share the same
lifecycle shape (lazy connect, single ``Authorization: Bearer`` header,
``aclose`` to release sockets) plus the same transport-error → typed
exception mapping. The wire-format protocol (NDJSON for Ollama, SSE for
OpenAI) and tool-call accumulation differ enough that ``chat_stream`` /
``embed`` stay in the per-provider files; this module only owns the
boilerplate that was demonstrably duplicated.

Internal to :mod:`service.llm` — leading underscore signals "do not
import from outside this package".
"""

from __future__ import annotations

import httpx

from service.llm.client import LLMUpstreamUnavailableError

__all__ = ["BaseHTTPLLMClient"]


class BaseHTTPLLMClient:
    """Lifecycle + transport-error helpers shared by all HTTP-backed LLM clients.

    Subclasses set ``_base_url`` / ``_chat_model`` / ``_embed_model`` /
    ``_timeout`` in their own ``__init__`` and override :meth:`_default_headers`
    when they need extra headers (e.g. OpenAI's ``OpenAI-Organization``).
    Everything else — `httpx` client construction, ``aclose``, the
    ``provider``-tagged ``LLMUpstreamUnavailableError`` wrap — is
    inherited as-is.

    Subclass ``__init__`` is responsible for setting every protected
    attribute below; the class-body defaults exist only so basedpyright
    sees a definite shape and so accidental "construct but never call
    super().__init__" wouldn't blow up on first attribute access.
    """

    #: Provider tag used in the wrapped transport-error message
    #: (``"ollama transport error: ..."``). Subclasses override.
    _provider: str = "llm"

    _base_url: str = ""
    _chat_model: str = ""
    _embed_model: str = ""
    _timeout: float = 120.0
    _api_key: str | None = None
    _client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Read-only properties — subclasses get these for free.
    # ------------------------------------------------------------------
    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def chat_model(self) -> str:
        return self._chat_model

    @property
    def embed_model(self) -> str:
        return self._embed_model

    @property
    def api_key(self) -> str | None:
        return self._api_key

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _default_headers(self) -> dict[str, str]:
        """Headers baked into the lazily-built ``httpx.AsyncClient``.

        Override to add provider-specific headers (e.g. organization).
        ``httpx`` bakes headers at construction time, so any change
        requires :meth:`aclose` + a re-create.
        """
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers=self._default_headers(),
            )
        return self._client

    async def aclose(self) -> None:
        """Release underlying network resources. Idempotent."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Transport-error wrapper
    # ------------------------------------------------------------------
    def _transport_error(self, exc: httpx.HTTPError) -> LLMUpstreamUnavailableError:
        """Build a provider-tagged transport-error exception.

        Helper rather than a context manager because async generators
        (``chat_stream``, ``pull_model``) prefer a plain ``try/except``
        re-raise — wrapping an async generator body in
        ``@asynccontextmanager`` has well-known interaction issues with
        ``yield`` and generator close-on-GC.

        Usage::

            try:
                async with client.stream(...): ...
            except httpx.HTTPError as exc:
                raise self._transport_error(exc) from exc
        """
        return LLMUpstreamUnavailableError(f"{self._provider} transport error: {exc}")
