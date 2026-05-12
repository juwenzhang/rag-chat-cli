"""Ollama implementation of :class:`core.llm.client.LLMClient`.

Uses ``httpx.AsyncClient`` to stream NDJSON from ``POST /api/chat`` and to
retrieve embeddings from ``POST /api/embeddings``. See the Ollama REST docs:
https://github.com/ollama/ollama/blob/main/docs/api.md

The client owns an :class:`httpx.AsyncClient` lazily; remember to ``await
client.aclose()`` at shutdown (done by ``app/chat_app.py``).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.llm.client import ChatChunk, ChatMessage, LLMError, ToolCall, ToolSpec


def _message_to_wire(m: ChatMessage) -> dict[str, Any]:
    """Serialize a :class:`ChatMessage` to the Ollama ``/api/chat`` shape.

    Hand-rolled (instead of ``dataclasses.asdict``) so we only emit fields
    that carry information — empty ``tool_calls`` and ``None`` ``tool_call_id``
    are dropped. This keeps the wire payload identical to the pre-P1.1 format
    for plain user/assistant turns.
    """
    out: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.tool_calls:
        out["tool_calls"] = [
            {
                "id": c.id,
                "function": {"name": c.name, "arguments": c.arguments},
            }
            for c in m.tool_calls
        ]
    if m.tool_call_id is not None:
        out["tool_call_id"] = m.tool_call_id
    return out


def _tool_to_wire(t: ToolSpec) -> dict[str, Any]:
    """Serialize a :class:`ToolSpec` to Ollama's ``tools[i]`` shape.

    Ollama follows the OpenAI tool-calling JSON: every tool is wrapped in
    ``{"type": "function", "function": {...}}``.
    """
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        },
    }


def _parse_tool_calls(msg: dict[str, Any]) -> tuple[ToolCall, ...]:
    """Parse Ollama's ``message.tool_calls`` array into :class:`ToolCall` objects.

    Ollama emits tool calls in the shape ``[{"function": {"name": ..., "arguments": {...}}}, ...]``
    and historically does not include an ``id`` per call. We synthesize a
    short uuid-based id so the ReAct orchestrator can correlate the matching
    ``role="tool"`` reply via ``ChatMessage.tool_call_id``.
    """
    raw = msg.get("tool_calls")
    if not isinstance(raw, list) or not raw:
        return ()
    parsed: list[ToolCall] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        fn = item.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name:
            continue
        args_raw = fn.get("arguments")
        if isinstance(args_raw, str):
            try:
                arguments = json.loads(args_raw) if args_raw else {}
            except json.JSONDecodeError:
                # Surface raw string under a sentinel key so callers can
                # still inspect what the model produced.
                arguments = {"__raw__": args_raw}
        elif isinstance(args_raw,
        dict):
            arguments = args_raw
        else:
            arguments = {}
        call_id = item.get("id")
        if not isinstance(call_id, str) or not call_id:
            call_id = f"call_{uuid.uuid4().hex[:12]}"
        parsed.append(ToolCall(id=call_id, name=name, arguments=arguments))
    return tuple(parsed)

__all__ = ["OllamaClient"]


class OllamaClient:
    """HTTP client for an Ollama server.

    Constructed directly or via :meth:`from_settings`. The constructor does
    **not** reach out to the network; the first call performs a lazy TCP
    connect.
    """

    def __init__(
        self,
        *,
        base_url: str,
        chat_model: str,
        embed_model: str,
        timeout: float = 120.0,
        api_key: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._chat_model = chat_model
        self._embed_model = embed_model
        self._timeout = timeout
        self._api_key = api_key
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------
    @classmethod
    def from_settings(cls, s: Any | None = None) -> OllamaClient:
        """Build from the global :mod:`settings` singleton (or an override)."""
        if s is None:
            from settings import settings as _s

            s = _s
        return cls(
            base_url=s.ollama.base_url,
            chat_model=s.ollama.chat_model,
            embed_model=s.ollama.embed_model,
            timeout=float(s.ollama.timeout),
            api_key=s.ollama.api_key,
        )

    # ------------------------------------------------------------------
    # Properties / dunders
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

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return f"OllamaClient(base_url={self._base_url!r}, chat_model={self._chat_model!r})"

    # ------------------------------------------------------------------
    # Internal plumbing
    # ------------------------------------------------------------------
    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers: dict[str, str] = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers=headers,
            )
        return self._client

    async def aclose(self) -> None:
        """Close the underlying :class:`httpx.AsyncClient`. Idempotent."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def set_api_key(self, api_key: str | None) -> None:
        """Update the Bearer token and recycle the underlying httpx client.

        ``httpx.AsyncClient`` headers are baked at construction time, so we
        close the existing client (if any) and let :meth:`_ensure_client`
        rebuild it lazily with the new ``Authorization`` header.
        """
        self._api_key = api_key
        await self.aclose()

    # ------------------------------------------------------------------
    # Public API — satisfies :class:`core.llm.client.LLMClient`
    # ------------------------------------------------------------------
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """Stream chat completions as :class:`ChatChunk` events.

        When ``tools`` is supplied, Ollama emits at most one ``tool_calls``
        array per turn (it does not partial-stream tool-call deltas the way
        OpenAI does). We surface each call as a single non-empty
        ``ChatChunk.tool_calls`` immediately, before the ``done`` terminator.

        Raises
        ------
        LLMError
            If the HTTP response is non-2xx or the body is not valid NDJSON.
        """

        payload: dict[str, Any] = {
            "model": model or self._chat_model,
            "messages": [_message_to_wire(m) for m in messages],
            "stream": True,
        }
        if tools:
            payload["tools"] = [_tool_to_wire(t) for t in tools]

        client = self._ensure_client()
        try:
            async with client.stream("POST", "/api/chat", json=payload) as resp:
                if resp.status_code >= 400:
                    body_bytes = await resp.aread()
                    body = body_bytes[:200].decode("utf-8", errors="replace")
                    # Same actionable rewrite as embed(): a 404 on a missing
                    # chat model is the single most common first-run error.
                    if resp.status_code == 404 and "not found" in body:
                        chat_model = payload.get("model") or self._chat_model
                        raise LLMError(
                            f"chat model {chat_model!r} is not pulled on this "
                            f"Ollama instance. Run: ollama pull {chat_model}"
                        )
                    raise LLMError(f"ollama /api/chat failed: {resp.status_code} {body!r}")
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise LLMError(f"ollama returned non-JSON line: {line[:200]!r}") from exc
                    delta = ""
                    tool_calls: tuple[ToolCall, ...] = ()
                    msg = data.get("message")
                    if isinstance(msg, dict):
                        delta = msg.get("content", "") or ""
                        tool_calls = _parse_tool_calls(msg)
                    done = bool(data.get("done"))
                    usage: dict[str, object] | None = None
                    if done:
                        # Ollama returns various *_count / *_duration fields
                        # when done=True; surface them as ``usage``.
                        usage = {
                            k: v
                            for k, v in data.items()
                            if k
                            in (
                                "total_duration",
                                "load_duration",
                                "prompt_eval_count",
                                "prompt_eval_duration",
                                "eval_count",
                                "eval_duration",
                            )
                        } or None
                    yield ChatChunk(
                        delta=delta,
                        done=done,
                        usage=usage,
                        tool_calls=tool_calls,
                    )
                    if done:
                        return
        except httpx.HTTPError as exc:
            raise LLMError(f"ollama transport error: {exc}") from exc

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """Return embedding vectors, one per input text."""

        client = self._ensure_client()
        target_model = model or self._embed_model
        vectors: list[list[float]] = []
        try:
            for text in texts:
                resp = await client.post(
                    "/api/embeddings",
                    json={"model": target_model, "prompt": text},
                )
                if resp.status_code >= 400:
                    body = resp.text[:200]
                    # Ollama returns 404 + ``"model ... not found"`` when the
                    # embed model isn't pulled. Rewrite to actionable advice
                    # so the user reaches for ``ollama pull`` instead of
                    # opening the source. ``try pulling it first`` is the
                    # literal upstream phrasing we sniff for here.
                    if resp.status_code == 404 and "not found" in body:
                        raise LLMError(
                            f"embed model {target_model!r} is not pulled on this "
                            f"Ollama instance. Run: ollama pull {target_model}"
                        )
                    raise LLMError(
                        f"ollama /api/embeddings failed: {resp.status_code} {body!r}"
                    )
                data = resp.json()
                embedding = data.get("embedding")
                if not isinstance(embedding, list):
                    raise LLMError(f"ollama /api/embeddings returned no embedding: {data!r}")
                vectors.append([float(x) for x in embedding])
        except httpx.HTTPError as exc:
            raise LLMError(f"ollama transport error: {exc}") from exc
        return vectors

    # ------------------------------------------------------------------
    # Connectivity probe — used by app/ to decide on Echo fallback
    # ------------------------------------------------------------------
    async def ping(self) -> bool:
        """Quick reachability check. Returns ``True`` if the server answers ``GET /``."""
        client = self._ensure_client()
        try:
            resp = await client.get("/", timeout=2.0)
        except httpx.HTTPError:
            return False
        return bool(resp.status_code < 500)

    async def list_models(self) -> list[str]:
        """Return names of models pulled on the Ollama server.

        Calls ``GET /api/tags``. On any transport error or non-2xx response
        the call returns ``[]`` so UI code can treat "empty list" as "no
        choices to offer" without special-casing exceptions.
        """
        client = self._ensure_client()
        try:
            resp = await client.get("/api/tags", timeout=5.0)
        except httpx.HTTPError:
            return []
        if resp.status_code >= 400:
            return []
        try:
            data = resp.json()
        except ValueError:
            return []
        models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(models, list):
            return []
        out: list[str] = []
        for m in models:
            if isinstance(m, dict):
                name = m.get("name")
                if isinstance(name, str) and name:
                    out.append(name)
        return out

    async def pull_model(
        self,
        name: str,
        *,
        insecure: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream pull progress for ``name`` (e.g. ``"qwen2.5:1.5b"``).

        Yields the raw NDJSON frames from ``POST /api/pull``. Common shapes:

          * ``{"status": "pulling manifest"}``
          * ``{"status": "downloading", "digest": "...", "total": N, "completed": M}``
          * ``{"status": "verifying sha256 digest"}``
          * ``{"status": "success"}``  (terminal — iterator stops after this)
          * ``{"error": "..."}``       (terminal)

        Pulling can take minutes to hours depending on size + network, so
        we override the per-request timeout (``read=None``) to disable the
        client-wide default and let the server keep the stream open.

        Raises
        ------
        LLMError
            On transport errors or non-2xx HTTP responses.
        """

        client = self._ensure_client()
        payload: dict[str, Any] = {"model": name, "stream": True}
        if insecure:
            payload["insecure"] = True
        # Disable read timeout for the long-lived download stream while
        # keeping connect/write timeouts at the client default.
        timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=5.0)
        try:
            async with client.stream("POST", "/api/pull", json=payload, timeout=timeout) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise LLMError(f"ollama /api/pull failed: {resp.status_code} {body[:200]!r}")
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise LLMError(f"ollama returned non-JSON line: {line[:200]!r}") from exc
                    if not isinstance(data, dict):
                        continue
                    yield data
                    if data.get("error") or data.get("status") == "success":
                        return
        except httpx.HTTPError as exc:
            raise LLMError(f"ollama transport error: {exc}") from exc
