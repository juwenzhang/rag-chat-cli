# Tasks: SSE + WebSocket Streaming

## 1. Protocol schema

- [ ] 1.1 新建 `api/streaming/__init__.py`。
- [ ] 1.2 `api/streaming/protocol.py`：`RetrievalHit` + 4 个 Event 类 + `StreamEvent` 判别联合。
- [ ] 1.3 `api/schemas/stream.py`：re-export `StreamEvent`（供 OpenAPI examples）。
- [ ] 1.4 单测：`TypeAdapter(StreamEvent).validate_python({"type":"token","delta":"x"})` 能拿到 `TokenEvent`。

## 2. SSE 工具

- [ ] 2.1 `api/streaming/sse.py`：`event_to_sse(evt) -> bytes`。
- [ ] 2.2 `merge_with_keepalive(stream, interval=15.0)`：`asyncio.wait_for` + 超时 ping；保证 cancel 安全。
- [ ] 2.3 单测：逐字节比对，含 `event:` + `data:` + `\n\n`。

## 3. Abort 工具

- [ ] 3.1 `api/streaming/abort.py`：`AbortContext` dataclass。
- [ ] 3.2 单测：多次 `abort()` 幂等；`aborted` 属性正确。

## 4. 增强 `ChatService.generate`

- [ ] 4.1 新增参数 `abort: AbortContext | None = None`。
- [ ] 4.2 每个 yield 前检查 `abort.aborted`，若是则 yield `ErrorEvent(code="ABORTED")` 并 return。
- [ ] 4.3 新增 `generate_full(session_id, text, *, use_rag) -> MessageOut`（聚合 token 事件），供 Change 6 非流式端点复用。
- [ ] 4.4 单测：`test_chat_service_abort.py`。

## 5. SSE 路由

- [ ] 5.1 `api/routers/chat_stream.py`：`POST /chat/stream` + `GET /chat/stream`（EventSource 用）。
- [ ] 5.2 POST body 用 `MessageIn`；GET 用 `Query` 参数。
- [ ] 5.3 响应头：`text/event-stream` + `no-cache` + `X-Accel-Buffering: no`。
- [ ] 5.4 对异常兜底：捕获 `Exception`，统一发 `ErrorEvent`。
- [ ] 5.5 `api/app.py` 挂 `chat_stream_router` 到 `/chat`。

## 6. WebSocket 路由

- [ ] 6.1 `api/routers/chat_ws.py`：`WebSocket /ws/chat` endpoint。
- [ ] 6.2 WS 鉴权 helper `async def authenticate_ws(ws) -> User`：
  - 优先读子协议 `bearer, <token>`，accept 时回 `subprotocol="bearer"`。
  - 回落读 query `?token=...`。
  - 失败 → `close(code=4401)` + return。
- [ ] 6.3 建立 reader 协程监听 `abort` 消息；主协程推 `generate` 事件。
- [ ] 6.4 客户端断开 → reader 捕 `WebSocketDisconnect` → `abort_ctx.abort()` → 主协程退出。
- [ ] 6.5 `api/app.py` 挂 ws 路由（FastAPI 的 ws 路由通过 `app.router.add_api_websocket_route` 或 `include_router`）。

## 7. CLI 端事件消费改造

- [ ] 7.1 `app/chat_app.py` 改为 `async for evt_dict in svc.generate(...)` + `TypeAdapter` 解析。
- [ ] 7.2 `view.append_token / render_retrieval / finalize / error` 四个方法明确对应四个事件。
- [ ] 7.3 Ctrl-C 触发 abort：在 `chat_app.py` 的主循环里捕获 KeyboardInterrupt，调 `abort_ctx.abort()`，允许当前回复中断、进入下一轮。
- [ ] 7.4 单测：FakeLLM + abort 流程，断言 CLI view 收到 `ABORTED` error。

## 8. AccessLog 脱敏

- [ ] 8.1 `api/middleware/logging.py` 增加 query 字段过滤：把 `token=`、`access_token=` 的值改为 `***`。
- [ ] 8.2 单测：构造 `Request`，断言日志字段不含原 token。

## 9. OpenAPI 示例

- [ ] 9.1 `POST /chat/stream` 在 docstring 中给出 SSE 响应示例（由于 FastAPI 对 text/event-stream 的描述有限，写在 `responses=` 参数）。
- [ ] 9.2 `WebSocket /ws/chat` 在 `docs/API.md` 单独描述，含 client → server / server → client 报文示例。

## 10. 测试

- [ ] 10.1 `tests/unit/api/streaming/` 三件：protocol / sse / abort。
- [ ] 10.2 `tests/unit/core/test_chat_service_abort.py`。
- [ ] 10.3 `tests/api/test_sse_stream.py`：使用 `httpx.AsyncClient.stream("POST", url, ...)` 消费。
- [ ] 10.4 `tests/api/test_ws_chat.py`：`TestClient(app).websocket_connect("/ws/chat?token=...")`。
- [ ] 10.5 `tests/api/test_ws_abort.py`：`send_json({"type":"abort"})` 后断言收到 ABORTED error。
- [ ] 10.6 `uv run pytest -q -k "stream or ws"` 全绿。

## 11. 质量与文档

- [ ] 11.1 `ruff check api/streaming api/routers/chat_stream.py api/routers/chat_ws.py` 无错。
- [ ] 11.2 `mypy --strict api/streaming` 无错。
- [ ] 11.3 `docs/API.md` 新增 "Streaming" 章节：SSE + WS 二选一、事件表、abort 语义。
- [ ] 11.4 AGENTS.md §19 Change Log 追加 "SSE + WS streaming"。

## 12. 冒烟

- [ ] 12.1 `python main.py serve --port 8001` 启动。
- [ ] 12.2 `curl -N -X POST http://localhost:8001/chat/stream -H 'Authorization: Bearer <token>' -H 'content-type: application/json' -d '{"session_id":"<sid>","content":"hello"}'` 能看到逐字输出。
- [ ] 12.3 `wscat -c 'ws://localhost:8001/ws/chat?token=<token>'` 发送 `user_message` 后接收流；再发 `{"type":"abort"}` 后立即收到 ABORTED error。
- [ ] 12.4 `python main.py chat` 在 CLI 中 Ctrl-C 能中断当前回复而不退出程序。
