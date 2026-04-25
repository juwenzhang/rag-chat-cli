# Tasks: SSE + WebSocket Streaming

## 1. Protocol schema

- [x] 1.1 新建 `api/streaming/__init__.py`（`__all__ = []`）。
- [x] 1.2 `api/streaming/protocol.py`：`RetrievalHit` + 4 个 Event 类 + `StreamEvent` 判别联合；`TypeAdapter(StreamEvent)` 缓存成模块级 `event_adapter`；便捷 `coerce_event(dict) -> StreamEvent`。
- [ ] 1.3 `api/schemas/stream.py` re-export。**N/A**：`api/streaming/protocol.py` 已直接导出；FastAPI 对 SSE/WS 端点的 OpenAPI 描述在 `responses=` 里用文案描述就够了，再加一层 re-export 只会把事实来源分裂。
- [x] 1.4 单测：`tests/unit/api/streaming/test_protocol.py`（5 条，含四种 event 类型 + 未知 type 报错）。

## 2. SSE 工具

- [x] 2.1 `api/streaming/sse.py`：`event_to_sse(evt) -> bytes`，使用 `event_adapter.dump_json` 保证单行 JSON。
- [x] 2.2 `merge_with_keepalive(stream, interval=15.0)`：`asyncio.create_task + asyncio.shield + wait_for` 实现"从最后一次产出算起的空闲超时"；`StopAsyncIteration` 用 sentinel `_END` 传递（task.result() 无法原生透传 StopAsyncIteration）；`finally` cancel 后台 task 保证 consumer 断开时不留尾巴。
- [x] 2.3 单测：`tests/unit/api/streaming/test_sse.py`（frame shape + 正常透传 + 空闲注入 ping + 早 break cancel 安全）。

## 3. Abort 工具

- [x] 3.1 `core/streaming/abort.py`：`AbortContext` dataclass（`asyncio.Event` 封装）。**放在 `core/` 而不是 `api/`**——`ChatService.generate` 要用它，而 `core` 不能 import `api`（AGENTS.md §3 红线）。
- [x] 3.2 单测 `tests/unit/core/streaming/test_abort.py`（3 条：初始 False / abort 幂等 / wait 返回）。

## 4. 增强 `ChatService.generate`

- [x] 4.1 新增参数 `abort: AbortContext | None = None`，位于 `top_k` 之后。
- [x] 4.2 每个 yield 前检查 `abort.aborted`；入口也做一次"预检"（abort 已设则根本不读历史 / 不拉 LLM）。命中时发 `{"type":"error","code":"ABORTED","message":"client aborted the stream"}` 并 return；**不持久化部分回复**（AGENTS.md §5.3 ABORTED 语义 + 避免被截断的 assistant 污染未来 context）。
- [x] 4.3 `generate_full(...)` 辅助方法：聚合 token → 单条 content，usage / duration_ms / error 一起返回（REST 非流式端点复用）。
- [x] 4.4 单测 `tests/unit/core/test_chat_service_abort.py`（4 条：中途 abort / 预 abort 短路 / generate_full 正常 / generate_full 上抛 error）。

## 5. SSE 路由

- [x] 5.1 `api/routers/chat_stream.py`：`POST /chat/stream`。
- [ ] 5.2 `GET /chat/stream`（EventSource 友好）。**推迟**：浏览器 EventSource 的 token-in-URL 方案本次未落地（`AccessLogMiddleware` 已做 query 脱敏为这条路径铺路）；Web 端第一版直接用 WS（推荐），真有需要再补 GET。
- [x] 5.3 响应头：`Cache-Control: no-cache, no-transform` + `X-Accel-Buffering: no` + `Connection: keep-alive`。
- [x] 5.4 异常兜底：`try/except` 包住 `service.generate(...)`，最后一帧发 `ErrorEvent(code="INTERNAL")`；`finally` 走 `service.aclose()` + 持久化已收到的 token。
- [x] 5.5 `api/app.py` 挂 `chat_stream_router` 到 `/chat`。

## 6. WebSocket 路由

- [x] 6.1 `api/routers/chat_ws.py`：`WebSocket /ws/chat`。
- [x] 6.2 WS 鉴权 helper `api.deps.authenticate_ws(ws) -> User | None`：
  - 优先读子协议 `bearer, <token>`，accept 时回 `subprotocol="bearer"`。
  - 回落读 query `?token=...`。
  - 失败 → `close(code=4401)` + 返回 None。
- [x] 6.3 Reader 协程监听 `{"type":"abort"}`；主协程用 `AbortContext` 轮询（`ChatService.generate` 的 abort 参数）。
- [x] 6.4 `WebSocketDisconnect` → reader 设 abort → 主协程下一帧停止；主协程 `finally` cancel reader task 并 dispose service。
- [x] 6.5 `api/app.py` 挂 ws 路由（`app.include_router(chat_ws_router.router)`，路由本身已带 `/ws/chat` 绝对路径）。

## 7. CLI 端事件消费改造

- [ ] 7.1 `app/chat_app.py` 改走 `TypeAdapter(StreamEvent).validate_python(...)`。**推迟到后续小 change**：当前 `ui.chat_view.Event` 是一个 `TypedDict`，已能消费 `ChatService.generate` 产出的 dict 流（127 条测试证明）；硬改成 pydantic 模型会把 UI 层拖进 pydantic 依赖，跨度过大。拆一个独立 change `cli-consume-stream-protocol` 后再做。
- [ ] 7.2 `view.append_token / render_retrieval / finalize / error` 方法明确对应。同上，并入 7.1 的后续 change。
- [ ] 7.3 Ctrl-C 触发 abort。同上。
- [ ] 7.4 单测：FakeLLM + abort。`tests/unit/core/test_chat_service_abort.py` 已覆盖等价核心逻辑；CLI 侧测试等 7.1 一并做。

## 8. AccessLog 脱敏

- [x] 8.1 `api/middleware/logging.py::_sanitize_query` 按 key（`token / access_token / refresh_token / jwt / password`，大小写不敏感）把值改为 `***`，其它 kv 保留；日志行额外新增 `query=` 字段。
- [x] 8.2 单测 `tests/unit/api/middleware/test_logging.py`（8 条：空串 / 纯无敏感 / 单敏感 / 多敏感 / 大小写 / URL-encoded value / 空值）。

## 9. OpenAPI 示例

- [x] 9.1 `POST /chat/stream` 的 `responses=` 里描述 SSE 事件协议（指向 AGENTS.md §5.3）。
- [ ] 9.2 `docs/API.md` WS 客户端/服务端报文示例。**推迟**：`docs/API.md` 暂未重写（见 P6 偏离记录）；`AGENTS.md §5.3` 已是唯一权威源，`README.md` 的 "REST API quick reference" 指到这里就够。

## 10. 测试

- [x] 10.1 `tests/unit/api/streaming/` 两件（protocol / sse）+ `tests/unit/core/streaming/test_abort.py` 一件。
- [x] 10.2 `tests/unit/core/test_chat_service_abort.py`。
- [x] 10.3 `tests/api/test_sse_stream.py`（3 条：未授权 401 / session 404 / happy 3 token + done）。用 `client.post` + 断言 `content-type: text/event-stream` + 自写 `_parse_sse` 把 body 分帧。
- [x] 10.4 `tests/api/test_ws_chat.py` happy path + 缺 token → 4401 关闭。
- [x] 10.5 `tests/api/test_ws_chat.py::test_ws_abort`：`send_json({"type":"abort"})` 后断言最终 `ErrorEvent(code="ABORTED")`。
- [x] 10.6 `tests/api/test_ws_chat.py::test_ws_subprotocol_auth`（参数化：`bearer, <tok>` 成功；反向组合允许失败但不崩）。
- [x] 10.7 `uv run pytest -q` 全绿（119 passed，87 + 32）。

## 11. 质量与文档

- [x] 11.1 `ruff check .` 全绿（per-file ignores 复用 P6 已有的 `api/routers/** = ["B008"]`）。
- [x] 11.2 `mypy --strict . --explicit-package-bases` 全绿（102 files）。
- [ ] 11.3 `docs/API.md` 新增 "Streaming" 章节。**同 §9.2，推迟**。
- [x] 11.4 AGENTS.md §19 Change Log 追加 v1.1 条目。

## 12. 冒烟

- [ ] 12.1 `python main.py serve --port 8001` 启动。**改由测试替代**：`tests/api/test_sse_stream.py` + `tests/api/test_ws_chat.py` 端到端驱动 `create_app()`，不占用本机端口。
- [ ] 12.2 `curl -N -X POST /chat/stream`。**同上**。
- [ ] 12.3 `wscat -c /ws/chat`。**同上**（`tests/api/test_ws_chat.py::test_ws_abort` 即是等价语义）。
- [ ] 12.4 `python main.py chat` Ctrl-C。**留给 CLI-consume-stream-protocol 后续 change 做**（§7 系列推迟对象）。
