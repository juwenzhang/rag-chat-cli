"""Ollama implementation of :class:`service.llm.client.LLMClient`.

Streams NDJSON from ``POST /api/chat`` and reads embeddings from
``POST /api/embed`` (with ``/api/embeddings`` fallback). REST docs:
https://github.com/ollama/ollama/blob/main/docs/api.md
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from service.llm._base_http import BaseHTTPLLMClient
from service.llm._http_errors import classify_http_error
from service.llm.client import (
    ChatChunk,
    ChatMessage,
    LLMError,
    ThinkingMode,
    ToolCall,
    ToolSpec,
)


def _message_to_wire(m: ChatMessage) -> dict[str, Any]:
    """Serialize :class:`ChatMessage` to Ollama's ``/api/chat`` shape.

    Hand-rolled (not ``asdict``) so empty tool fields are dropped — keeps
    the wire payload identical to the pre-tools shape for plain turns.
    """
    out: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.thinking:
        out["thinking"] = m.thinking
    if m.image_urls:
        out["images"] = [_image_url_to_ollama_payload(image_url) for image_url in m.image_urls]
    if m.tool_calls:
        out["tool_calls"] = [
            {"id": c.id, "function": {"name": c.name, "arguments": c.arguments}}
            for c in m.tool_calls
        ]
    if m.tool_call_id is not None:
        out["tool_call_id"] = m.tool_call_id
    if m.tool_name is not None:
        out["tool_name"] = m.tool_name
    return out


def _image_url_to_ollama_payload(image_url: str) -> str:
    if image_url.startswith("data:"):
        _prefix, _sep, payload = image_url.partition(",")
        return payload
    return image_url


def _tool_to_wire(t: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
    }


def _parse_tool_calls(msg: dict[str, Any]) -> tuple[ToolCall, ...]:
    """Parse Ollama's ``message.tool_calls`` array.

    Ollama omits per-call ids; we synthesize one so the ReAct orchestrator
    can correlate the matching ``role="tool"`` reply via ``tool_call_id``.
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
                arguments = {"__raw__": args_raw}
        elif isinstance(args_raw, dict):
            arguments = args_raw
        else:
            arguments = {}
        call_id = item.get("id")
        if not isinstance(call_id, str) or not call_id:
            call_id = f"call_{uuid.uuid4().hex[:12]}"
        parsed.append(ToolCall(id=call_id, name=name, arguments=arguments))
    return tuple(parsed)


__all__ = ["OllamaClient"]


class OllamaClient(BaseHTTPLLMClient):
    """HTTP client for an Ollama server.

    Construction is cheap; the underlying ``httpx.AsyncClient`` is created
    lazily on first call. Remember ``await client.aclose()`` at shutdown.
    """

    _provider = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        chat_model: str,
        embed_model: str,
        timeout: float = 120.0,
        api_key: str | None = None,
        think: ThinkingMode | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._chat_model = chat_model
        self._embed_model = embed_model
        self._timeout = timeout
        self._api_key = api_key
        self._think = think
        self._client = None

    @classmethod
    def from_settings(cls, s: Any | None = None) -> OllamaClient:
        if s is None:
            from settings import settings as _s

            s = _s
        return cls(
            base_url=s.ollama.base_url,
            chat_model=s.ollama.chat_model,
            embed_model=s.ollama.embed_model,
            timeout=float(s.ollama.timeout),
            api_key=s.ollama.api_key,
            think=s.ollama.think,
        )

    def __repr__(self) -> str:  # pragma: no cover
        return f"OllamaClient(base_url={self._base_url!r}, chat_model={self._chat_model!r})"

    async def set_api_key(self, api_key: str | None) -> None:
        """Update the Bearer token; recycles the underlying httpx client.

        ``httpx`` bakes headers at construction, so we must close + rebuild.
        """
        self._api_key = api_key
        await self.aclose()

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        tools: list[ToolSpec] | None = None,
        think: ThinkingMode | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """Stream chat completions as :class:`ChatChunk` events.

        Tool calls arrive whole (Ollama doesn't partial-stream them), so each
        is yielded immediately on a single non-empty ``tool_calls`` chunk
        before the ``done`` terminator.

        Raises :class:`LLMError` (or a subclass) on non-2xx HTTP and on
        invalid NDJSON.
        """

        payload: dict[str, Any] = {
            "model": model or self._chat_model,
            "messages": [_message_to_wire(m) for m in messages],
            "stream": True,
        }
        if tools:
            payload["tools"] = [_tool_to_wire(t) for t in tools]
        effective_think = self._think if think is None else think
        if effective_think is not None:
            payload["think"] = effective_think

        client = self._ensure_client()
        try:
            async with client.stream("POST", "/api/chat", json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise classify_http_error(
                        provider="ollama",
                        status=resp.status_code,
                        headers=resp.headers,
                        body=body,
                    )
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise LLMError(f"ollama returned non-JSON line: {line[:200]!r}") from exc
                    delta = ""
                    thinking = ""
                    tool_calls: tuple[ToolCall, ...] = ()
                    msg = data.get("message")
                    if isinstance(msg, dict):
                        thinking = msg.get("thinking", "") or ""
                        delta = msg.get("content", "") or ""
                        tool_calls = _parse_tool_calls(msg)
                    done = bool(data.get("done"))
                    usage: dict[str, object] | None = None
                    if done:
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
                        thinking=thinking,
                        done=done,
                        usage=usage,
                        tool_calls=tool_calls,
                    )
                    if done:
                        return
        except httpx.HTTPError as exc:
            raise self._transport_error(exc) from exc

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """Return embedding vectors, one per input text.

        Tries ``POST /api/embed`` (batch) first, falls back to the older
        ``POST /api/embeddings`` (single-prompt) on 404 for compatibility
        with older Ollama builds.
        """

        client = self._ensure_client()
        target_model = model or self._embed_model
        try:
            resp = await client.post(
                "/api/embed",
                json={"model": target_model, "input": texts, "truncate": True},
            )
            if resp.status_code < 400:
                data = resp.json()
                embeddings = data.get("embeddings")
                if isinstance(embeddings, list):
                    return [
                        [float(x) for x in item] for item in embeddings if isinstance(item, list)
                    ]
            elif resp.status_code != 404:
                raise classify_http_error(
                    provider="ollama",
                    status=resp.status_code,
                    headers=resp.headers,
                    body=resp.text,
                )

            vectors: list[list[float]] = []
            for text in texts:
                resp = await client.post(
                    "/api/embeddings",
                    json={"model": target_model, "prompt": text},
                )
                if resp.status_code >= 400:
                    raise classify_http_error(
                        provider="ollama",
                        status=resp.status_code,
                        headers=resp.headers,
                        body=resp.text,
                    )
                data = resp.json()
                embedding = data.get("embedding")
                if not isinstance(embedding, list):
                    raise LLMError(f"ollama /api/embeddings returned no embedding: {data!r}")
                vectors.append([float(x) for x in embedding])
        except httpx.HTTPError as exc:
            raise self._transport_error(exc) from exc
        return vectors

    async def ping(self) -> bool:
        """Quick reachability check against ``GET /``."""
        client = self._ensure_client()
        try:
            resp = await client.get("/", timeout=2.0)
        except httpx.HTTPError:
            return False
        return bool(resp.status_code < 500)

    async def list_models(self) -> list[str]:
        """Return names of models available on the server (``GET /api/tags``).

        Returns ``[]`` on any transport error or non-2xx response so UI code
        can treat "empty list" uniformly without special-casing exceptions.
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
        """Stream pull progress for ``name`` (e.g. ``"qwen3-coder-next:cloud"``).

        Yields raw NDJSON frames from ``POST /api/pull`` (statuses like
        ``pulling manifest`` / ``downloading`` / ``success`` / ``error``).
        Read timeout is disabled because pulls can take minutes to hours.
        """

        client = self._ensure_client()
        payload: dict[str, Any] = {"model": name, "stream": True}
        if insecure:
            payload["insecure"] = True
        timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=5.0)
        try:
            async with client.stream("POST", "/api/pull", json=payload, timeout=timeout) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise classify_http_error(
                        provider="ollama",
                        status=resp.status_code,
                        headers=resp.headers,
                        body=body,
                    )
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
            raise self._transport_error(exc) from exc
