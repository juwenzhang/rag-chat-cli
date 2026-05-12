# Chat Stream Protocol

Wire format for the two streaming surfaces:

| Surface | Transport | Direction | Endpoint |
|---|---|---|---|
| **SSE** | `text/event-stream` over HTTP | server → client only | `POST /chat/stream` |
| **WebSocket** | JSON frames | bidirectional | `GET /ws/chat` (upgrade) |

Both share **one event schema** — defined as a discriminated Pydantic
union in `api/streaming/protocol.py` and as a `TypedDict` in
`core/streaming/events.py`. Add fields in those two files and every
surface inherits them automatically.

CLI / REPL consumes the same vocabulary via `ChatService.generate(...)`
yielding the same dicts; SSE/WS are just transports.

---

## Event vocabulary

Each event has a `type` discriminator plus a disjoint subset of fields.
Pre-P1 events (`retrieval / token / done / error`) are unchanged from
v1.x — P1.5 (#6) added `thought / tool_call / tool_result`, P1.4 (#5)
introduced the ordering rules in the ReAct loop.

### `retrieval`
Emitted at most once per turn, before any `token` event, when
`use_rag=true` and a `KnowledgeBase` is configured.

```json
{
  "type": "retrieval",
  "hits": [
    {
      "document_id": "uuid-or-null",
      "title": "Eiffel Tower",
      "snippet": "completed in 1889 …",
      "score": 0.83,
      "source": "/notes/paris.md"
    }
  ]
}
```

The numbering of `hits[i]` matches the `[1] / [2]` markers the assistant
is asked to cite — see `core/prompts.py:PromptBuilder`.

### `token`
Incremental assistant text. Emitted any number of times per turn.

```json
{ "type": "token", "delta": "the answer is " }
```

Concatenating every `delta` in receive order reconstructs the assistant's
final text for **the current iteration** of the ReAct loop. Tool-flavoured
intermediate iterations may emit zero `token` events.

### `thought` (P1.5, optional)
Model reasoning content — only emitted by providers / models that surface
explicit "thinking" output (e.g. `<think>…</think>` tags, OpenAI o-series).
Skip if you don't have a UI affordance for it.

```json
{ "type": "thought", "text": "I should look up the weather first." }
```

### `tool_call` (P1.5)
The model has requested one tool invocation. Emitted **before** the host
executes the tool — clients can render an "executing X(…)" indicator
during the round-trip.

```json
{
  "type": "tool_call",
  "tool_call_id": "call_3f9e8b1c",
  "tool_name": "get_weather",
  "arguments": { "city": "Tokyo" }
}
```

Tool calls inside a single ReAct iteration are emitted in order; multiple
calls per iteration are dispatched sequentially and each gets its own
matching `tool_result`.

### `tool_result` (P1.5)
The host has dispatched the tool. `content` is the string fed back to the
LLM as the `role="tool"` message body — UIs typically render it inline
beneath the matching `tool_call`. On `is_error=true` the model is told the
call failed and may retry or change approach.

```json
{
  "type": "tool_result",
  "tool_call_id": "call_3f9e8b1c",
  "tool_name": "get_weather",
  "content": "{\"temp_c\": 18, \"condition\": \"cloudy\"}",
  "is_error": false
}
```

### `done`
Terminal happy-path event. Exactly one per generate() invocation.

```json
{
  "type": "done",
  "message_id": "uuid-or-null",
  "duration_ms": 1842,
  "usage": { "eval_count": 187, "prompt_eval_count": 412 }
}
```

`usage` is provider-shape (Ollama uses `eval_count` / `prompt_eval_count`;
multi-provider adapter in #20 will normalise this).

### `error`
Terminal failure. Exactly one per generate() invocation, in lieu of `done`.

```json
{
  "type": "error",
  "code": "max_steps_reached",
  "message": "agent exceeded 5 reasoning steps"
}
```

Defined `code` values (informational, not exhaustive):

| code | meaning |
|---|---|
| `ABORTED` | client invoked abort (WS `{type:"abort"}`, HTTP disconnect) |
| `llm_error` | upstream LLM provider returned non-2xx / malformed |
| `retrieval_failed` | KnowledgeBase.search raised |
| `memory_read_failed` / `memory_write_failed` | chat-memory IO |
| `max_steps_reached` | ReAct loop bound hit without a tool-free reply |
| `PROTOCOL` | malformed event surfaced by `coerce_event` (transport-level) |
| `INTERNAL` | unhandled exception in the router |
| `unexpected` | unhandled exception inside `ChatService.generate` |

---

## Ordering rules (ReAct loop)

For one `generate()` invocation:

```
[retrieval]?
( [token]*  [tool_call+ tool_result+]?  )+
( done | error )
```

Translated:

1. **At most one `retrieval` event**, before anything else.
2. A `token` stream **then** zero-or-more `tool_call` / `tool_result`
   pairs constitutes one ReAct iteration. The loop repeats until either:
   * the assistant emits a tool-free turn (`done` fires), or
   * `max_steps` is exhausted (`error` with `code: max_steps_reached`).
3. **Exactly one terminator** (`done` or `error`).

Consumers should be tolerant of unknown event types (skip + log) so future
additions remain backward-compatible — clients that don't yet handle
`thought` will still render perfectly readable transcripts.

---

## SSE framing

Each event becomes one SSE frame:

```
event: token
data: {"type":"token","delta":"hello "}

```

Frames are separated by `\n\n`. The router emits a keepalive comment frame
(`: keepalive\n\n`) every ~15 s through `merge_with_keepalive` so idle
proxies don't kill the connection. Clients should ignore comment frames.

## WebSocket framing

Each event is one JSON object sent via `ws.send_json(...)`. The client
may at any time send `{"type":"abort"}` to cancel the current generation
(server flips `AbortContext`; in-flight tokens drop, no assistant turn is
persisted). Closing the socket is equivalent to abort.

## Versioning

Events are **additive-by-default**: new event types may appear at any
time (P1.5 introduced three). Clients should treat unknown `type` values
as no-ops. Field renames or removals from existing event types are
breaking and would warrant an explicit protocol-version negotiation —
none planned.
