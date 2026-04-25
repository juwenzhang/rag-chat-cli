# Design: SSE + WebSocket Streaming

## Context

AGENTS.md §5.3 定义的事件协议（必须严格遵守，CLI/Web/API 三端共用）：

```json
{"type": "retrieval", "hits": [{"document_id": "...", "title": "...", "snippet": "...", "score": 0.82}]}
{"type": "token", "delta": "Hello"}
{"type": "token", "delta": ", world"}
{"type": "done", "message_id": "uuid", "usage": {"prompt_tokens": 42, "completion_tokens": 17}}
{"type": "error", "code": "OLLAMA_UNAVAILABLE", "message": "..."}
```

Change 3 的 `ChatService.generate(session_id, user_text, *, use_rag) -> AsyncIterator[Event]` 已经产出上述字典流。本次负责**传输层**：SSE / WS / CLI 三种消费端。

## Goals / Non-Goals

**Goals**
- **Single Source of Truth**：`api/streaming/protocol.py` 定义事件 schema，三端都 import 它。
- **正确的 SSE 语义**：`data:` 前缀、空行分隔、正确处理多行 JSON 用 `\n` 问题（统一单行 JSON）。
- **WebSocket abort**：客户端 `{"type":"abort"}` 到达后，服务端**立即**停止 LLM 拉取并发 `{"type":"error","code":"ABORTED"}`。
- **keepalive**：SSE 每 15s 发 `:ping\n\n`；WS 依赖 ping/pong。
- **背压**：当客户端读慢时，服务端不无限缓冲（httpx/uvicorn 默认 OK，verify）。

**Non-Goals**
- 不做 resume / Last-Event-ID。
- 不做多 tab 同步。

## Architecture

### `api/streaming/protocol.py`

```python
class RetrievalHit(BaseModel):
    document_id: str
    title: str | None = None
    snippet: str
    score: float

class RetrievalEvent(BaseModel):
    type: Literal["retrieval"] = "retrieval"
    hits: list[RetrievalHit]

class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    delta: str

class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    message_id: str
    usage: dict | None = None

class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str

StreamEvent = Annotated[
    RetrievalEvent | TokenEvent | DoneEvent | ErrorEvent,
    Field(discriminator="type"),
]
```

### `api/streaming/sse.py`

```python
def event_to_sse(evt: StreamEvent) -> bytes:
    payload = evt.model_dump_json()
    # SSE 规范：data 字段若含换行要逐行 "data:"；我们序列化 JSON 保证单行。
    return f"event: {evt.type}\ndata: {payload}\n\n".encode("utf-8")

async def sse_keepalive(interval: float = 15.0) -> AsyncIterator[bytes]:
    while True:
        await asyncio.sleep(interval); yield b":ping\n\n"

async def merge_with_keepalive(
    stream: AsyncIterator[bytes], interval: float = 15.0
) -> AsyncIterator[bytes]:
    """当 stream 空闲 > interval 时插入 ping 防止代理关连接。"""
```

### `api/streaming/abort.py`

```python
@dataclass
class AbortContext:
    event: asyncio.Event = field(default_factory=asyncio.Event)

    def abort(self) -> None: self.event.set()
    @property
    def aborted(self) -> bool: return self.event.is_set()
    async def wait(self) -> None: await self.event.wait()
```

### `core/chat_service.py` 增强

```python
async def generate(
    self, session_id: str, user_text: str, *,
    use_rag: bool = False, abort: AbortContext | None = None,
) -> AsyncIterator[dict]:
    # 1. retrieval
    # 2. 调 llm.chat_stream(...)，在 loop 中：
    #    async for chunk in self._llm.chat_stream(messages):
    #        if abort and abort.aborted:
    #            yield {"type":"error","code":"ABORTED","message":"client aborted"}
    #            return
    #        yield {"type":"token","delta":chunk.delta}
    # 3. done
```

**注意**：Ollama 的 NDJSON 流是服务端推，客户端无法"取消"单个请求；我们在**读取方**提前 `return` + `await httpx_response.aclose()` 即可停止下载。`OllamaClient.chat_stream` 内部用 `async with client.stream(...)` 做上下文管理，保证 aclose 正确。

### `routers/chat_stream.py`（SSE）

```python
router = APIRouter()

@router.post("/stream")
async def chat_stream(
    body: MessageIn,
    user: User = Depends(get_current_user),
    svc: ChatService = Depends(get_chat_service),
):
    async def gen() -> AsyncIterator[bytes]:
        try:
            async for evt_dict in svc.generate(
                body.session_id, body.content, use_rag=body.use_rag
            ):
                evt = TypeAdapter(StreamEvent).validate_python(evt_dict)
                yield event_to_sse(evt)
        except Exception as e:
            err = ErrorEvent(code="INTERNAL", message=str(e))
            yield event_to_sse(err)

    return StreamingResponse(
        merge_with_keepalive(gen()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )
```

EventSource GET 版：从 query 读 `session_id`, `q`，token 走 `access_token` query（EventSource 不能自定义 header）。**注意**：`access_token in URL` 可能被日志记录；Change 10 的 Nginx 配置要把它从 access log 擦除，本 change 在 `AccessLogMiddleware` 先做 URL sanitize。

### `routers/chat_ws.py`（WebSocket）

```python
router = APIRouter()

@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket, session_mgr=Depends(get_ws_session)):
    # session_mgr 负责：
    #   1. 通过 query 的 access_token 鉴权（因为 WS 握手不带 Authorization header 不总方便）
    #   2. 拿 current_user
    await ws.accept()
    abort_ctx = AbortContext()

    async def reader():
        try:
            while True:
                msg = await ws.receive_json()
                if msg.get("type") == "abort":
                    abort_ctx.abort(); return
        except WebSocketDisconnect:
            abort_ctx.abort()

    reader_task = asyncio.create_task(reader())
    try:
        first = await ws.receive_json()  # 期望 user_message
        if first.get("type") != "user_message":
            await ws.send_json({"type":"error","code":"PROTOCOL","message":"expect user_message"})
            await ws.close(); return

        async for evt in svc.generate(first["session_id"], first["content"],
                                      use_rag=first.get("use_rag", False),
                                      abort=abort_ctx):
            await ws.send_json(evt)
    finally:
        reader_task.cancel()
        with contextlib.suppress(Exception): await ws.close()
```

**鉴权**：建立 WS 连接时，支持两种方式：
1. Query `?token=<access>`（浏览器 `new WebSocket("ws://.../ws/chat?token=...")` 唯一途径）。
2. 子协议 `Sec-WebSocket-Protocol: bearer, <token>`（更安全）。

优先读 header/子协议，回落 query。

### CLI 端共用 protocol

`app/chat_app.py` 的事件循环：

```python
async for evt_dict in svc.generate(session_id, text, use_rag=...):
    evt = TypeAdapter(StreamEvent).validate_python(evt_dict)
    match evt.type:
        case "retrieval": view.render_retrieval(evt.hits)
        case "token":     view.append_token(evt.delta)
        case "done":      view.finalize(evt.message_id, evt.usage)
        case "error":     view.error(evt.code, evt.message)
```

这样 CLI 与 Web 共享事件定义，任何字段新增只改 `protocol.py` 一处。

## Alternatives Considered

- **sse-starlette 库**：省事，但多一层抽象，我们手写足够简洁。
- **只做 WS 不做 SSE**：前端简单场景用 EventSource 更轻；两者都支持，让前端自由选择。
- **gRPC-web**：overkill。

## Risks & Mitigations

- **WS abort 语义**：reader 与 writer 并行，共享 `AbortContext`；reader 收 abort 后 writer 在下一次 yield 前停止。最坏情况滞后 1 个 token。
  **缓解**：可接受；若要严格即停，把 `OllamaClient.chat_stream` 包在 `asyncio.wait({llm_task, abort_task}, return_when=FIRST_COMPLETED)`，但会增加复杂度，暂不做。
- **SSE 代理缓冲**：Nginx 默认会缓冲。
  **缓解**：响应头 `X-Accel-Buffering: no`；Nginx 侧配置 `proxy_buffering off;`（Change 10 做）。
- **token in URL**：EventSource 强制。
  **缓解**：①  `AccessLogMiddleware` 擦除 query 中 `token=`；② 文档推荐 Web 端优先用 WS，SSE-with-token-in-URL 仅作兼容方案。

## Testing Strategy

- 单元：
  - `tests/unit/api/streaming/test_sse_format.py`：`event_to_sse(...)` 字节与期望逐字节匹配。
  - `tests/unit/api/streaming/test_protocol.py`：`TypeAdapter(StreamEvent).validate_python(...)` 四种类型 round-trip。
  - `tests/unit/core/test_chat_service_abort.py`：构造 FakeLLM 吐 100 个 token，半程 `abort_ctx.abort()`，断言最终 event 流以 `error code=ABORTED` 结尾，且 token 数 < 100。
- 集成：
  - `tests/api/test_sse_stream.py`：`httpx.AsyncClient` + `stream=True` 消费 SSE，断言收到 4 种 event 至少各 1 个。
  - `tests/api/test_ws_chat.py`：`starlette.testclient.TestClient` 的 `websocket_connect`，收发 + abort 流程。
- 负向：
  - WS 未带 token → 1008 关闭。
  - SSE token 过期 → 流还没开始就 401。
  - 客户端断开连接 → 服务端 30s 内释放资源（通过 `tracemalloc` 或简单的 active_count 计数）。
