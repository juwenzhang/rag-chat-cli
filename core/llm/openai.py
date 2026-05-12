"""OpenAI-compatible :class:`core.llm.client.LLMClient` (#20 P5.1).

Targets the canonical ``/v1/chat/completions`` + ``/v1/embeddings`` REST
shapes. Works against:

* OpenAI proper (``https://api.openai.com/v1``)
* Any OpenAI-compatible server: vLLM, LM Studio, llama.cpp, Together, Groq,
  Mistral, Fireworks, DeepSeek, Anyscale, …

Streaming uses SSE-style ``data:`` lines. Tool calls arrive as **per-index
incremental deltas** (unlike Ollama which emits them whole) — we accumulate
per-index buffers and emit a complete :class:`~core.llm.client.ToolCall`
the moment a finish reason or terminator is seen.

Construction picks settings out of the dedicated ``OpenAISettings`` group;
adding a second OpenAI-compatible endpoint just means another
:class:`OpenAIClient` instance with overridden ``base_url`` / ``api_key`` /
``chat_model``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.llm.client import ChatChunk, ChatMessage, LLMError, ToolCall, ToolSpec

__all__ = ["OpenAIClient"]


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _message_to_wire(m: ChatMessage) -> dict[str, Any]:
    """Render a :class:`ChatMessage` to OpenAI's ``messages[i]`` shape.

    OpenAI requires ``tool_calls[i].function.arguments`` to be a JSON
    **string**, not an object — that's the one wire difference from how
    we hold the data internally.
    """
    out: dict[str, Any] = {"role": m.role, "content": m.content or ""}
    if m.tool_calls:
        out["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {
                    "name": c.name,
                    "arguments": json.dumps(c.arguments, ensure_ascii=False),
                },
            }
            for c in m.tool_calls
        ]
    if m.tool_call_id is not None:
        out["tool_call_id"] = m.tool_call_id
    return out


def _tool_to_wire(t: ToolSpec) -> dict[str, Any]:
    """OpenAI's ``tools[i]`` shape — same envelope as our Ollama serializer."""
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        },
    }


# ---------------------------------------------------------------------------
# Tool-call accumulator
# ---------------------------------------------------------------------------


class _ToolCallBuilder:
    """Per-stream accumulator for OpenAI's incremental ``tool_calls`` deltas.

    The model can interleave multiple tool calls (each at a different
    ``index``); arguments arrive as JSON-string fragments that must be
    concatenated in order before parsing. We hold every in-flight call by
    index and finalise on the terminator chunk.
    """

    def __init__(self) -> None:
        self._buf: dict[int, dict[str, Any]] = {}

    def feed(self, raw: list[dict[str, Any]]) -> None:
        for item in raw:
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            if not isinstance(idx, int):
                continue
            entry = self._buf.setdefault(idx, {"id": None, "name": "", "args": ""})
            if "id" in item and isinstance(item["id"], str):
                entry["id"] = item["id"]
            fn = item.get("function")
            if isinstance(fn, dict):
                name = fn.get("name")
                if isinstance(name, str):
                    entry["name"] += name
                args = fn.get("arguments")
                if isinstance(args, str):
                    entry["args"] += args

    def take_all(self) -> tuple[ToolCall, ...]:
        """Finalize everything buffered so far and reset.

        Malformed entries (no name, broken JSON args) are dropped silently
        — the LLM will see "no tool result" and can retry; better than a
        hard error mid-stream.
        """
        out: list[ToolCall] = []
        for idx in sorted(self._buf):
            entry = self._buf[idx]
            name = entry["name"]
            if not name:
                continue
            try:
                arguments = json.loads(entry["args"]) if entry["args"] else {}
            except json.JSONDecodeError:
                arguments = {"__raw__": entry["args"]}
            if not isinstance(arguments, dict):
                arguments = {"__value__": arguments}
            call_id = entry["id"] or f"call_idx{idx}"
            out.append(ToolCall(id=call_id, name=name, arguments=arguments))
        self._buf.clear()
        return tuple(out)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class OpenAIClient:
    """Async HTTP client speaking the OpenAI v1 wire format.

    Construct directly or via :meth:`from_settings`. The constructor does
    **not** open a network connection; the first ``chat_stream`` /
    ``embed`` call performs lazy TCP setup.

    ``api_key`` is required for the real OpenAI endpoint and ignored by
    most local-OpenAI-compatible servers (we still send the header
    unconditionally when set — harmless for the local case).
    """

    def __init__(
        self,
        *,
        base_url: str,
        chat_model: str,
        embed_model: str,
        api_key: str | None = None,
        timeout: float = 120.0,
        organization: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._chat_model = chat_model
        self._embed_model = embed_model
        self._api_key = api_key
        self._timeout = timeout
        self._organization = organization
        self._client: httpx.AsyncClient | None = None

    @classmethod
    def from_settings(cls, s: Any | None = None) -> OpenAIClient:
        if s is None:
            from settings import settings as _s

            s = _s
        return cls(
            base_url=s.openai.base_url,
            chat_model=s.openai.chat_model,
            embed_model=s.openai.embed_model,
            api_key=s.openai.api_key,
            timeout=float(s.openai.timeout),
            organization=s.openai.organization,
        )

    # ------------------------------------------------------------------
    # Properties
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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers: dict[str, str] = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            if self._organization:
                headers["OpenAI-Organization"] = self._organization
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers=headers,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # LLMClient
    # ------------------------------------------------------------------
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """Stream chat completions as :class:`ChatChunk` events.

        Raises
        ------
        LLMError
            On non-2xx HTTP, malformed SSE line, or transport failure.
        """

        payload: dict[str, Any] = {
            "model": model or self._chat_model,
            "messages": [_message_to_wire(m) for m in messages],
            "stream": True,
            # Ask the server to include token usage in the final chunk —
            # not all OpenAI-compatible backends honour this, but it's
            # cheap to request.
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = [_tool_to_wire(t) for t in tools]
            payload["tool_choice"] = "auto"

        client = self._ensure_client()
        builder = _ToolCallBuilder()
        usage: dict[str, object] | None = None
        finished = False

        try:
            async with client.stream(
                "POST",
                "/v1/chat/completions",
                json=payload,
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise LLMError(
                        f"openai chat completions failed: "
                        f"{resp.status_code} {body[:200]!r}"
                    )
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    # SSE comments start with ``:`` — Anthropic-style proxies
                    # use them as keep-alives. Skip silently.
                    if line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        line = line[len("data:") :].strip()
                    if line == "[DONE]":
                        # Some servers (vLLM) emit [DONE] before a usage
                        # chunk; treat as a terminator marker and break
                        # only after we've flushed any pending tool_calls.
                        finished = True
                        break
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise LLMError(
                            f"openai returned non-JSON SSE line: {line[:200]!r}"
                        ) from exc

                    # Usage-only chunk (last frame from servers that honour
                    # ``include_usage``). No choices array.
                    if not chunk.get("choices"):
                        u = chunk.get("usage")
                        if isinstance(u, dict):
                            usage = dict(u)
                        continue

                    choice = chunk["choices"][0]
                    delta = choice.get("delta") or {}
                    text = delta.get("content")
                    if isinstance(text, str) and text:
                        yield ChatChunk(delta=text)
                    raw_tc = delta.get("tool_calls")
                    if isinstance(raw_tc, list) and raw_tc:
                        builder.feed(raw_tc)
                    finish = choice.get("finish_reason")
                    if finish is not None:
                        # Flush any accumulated tool_calls before signalling done.
                        tcs = builder.take_all()
                        if tcs:
                            yield ChatChunk(tool_calls=tcs)
                        finished = True
                        # Don't break here — let the loop catch [DONE] or
                        # a trailing usage frame, so ``usage`` is populated.
        except httpx.HTTPError as exc:
            raise LLMError(f"openai transport error: {exc}") from exc

        # Drain any tool_calls that arrived without a finish_reason
        # (some servers omit finish_reason on tool calls and rely on
        # [DONE] alone). Then emit the terminator.
        leftovers = builder.take_all()
        if leftovers:
            yield ChatChunk(tool_calls=leftovers)
        if finished or usage is not None:
            yield ChatChunk(done=True, usage=usage)

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """Batch-embed via ``POST /v1/embeddings``.

        OpenAI accepts a list as ``input``, unlike Ollama which embeds one
        prompt per call. We send the whole batch in a single request.
        """
        if not texts:
            return []
        client = self._ensure_client()
        try:
            resp = await client.post(
                "/v1/embeddings",
                json={
                    "model": model or self._embed_model,
                    "input": texts,
                },
            )
            if resp.status_code >= 400:
                raise LLMError(
                    f"openai embeddings failed: "
                    f"{resp.status_code} {resp.text[:200]!r}"
                )
            data = resp.json()
            entries = data.get("data")
            if not isinstance(entries, list):
                raise LLMError(f"openai embeddings: malformed body: {data!r}")
            # Reorder by ``index`` because OpenAI promises but doesn't
            # always deliver insertion order on every implementation.
            entries.sort(key=lambda e: int(e.get("index", 0)))
            return [
                [float(x) for x in e.get("embedding", [])]
                for e in entries
            ]
        except httpx.HTTPError as exc:
            raise LLMError(f"openai transport error: {exc}") from exc
