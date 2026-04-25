# Proposal: SSE + WebSocket Streaming Chat

## Why

AGENTS.md §5.2 + §5.3 明确要求：

> `POST /chat/stream` —— SSE 流式输出
> `WebSocket /ws/chat` —— 双向，支持客户端中断（`{"type":"abort"}`）
> 统一事件协议：`retrieval / token / done / error`
> 前端必须能显示"检索卡片 + 流式 token + 结束 usage"。

Change 6 已把非流式 REST 做完，但**流式能力是 AI 对话体验的核心**——没有流式，前端只能转圈。§15 P5 阶段必须补齐 SSE + WS 才能支撑 Change 12-14 的 Web 对话界面。

当前 `ChatService.generate()`（Change 3）已经返回 `AsyncIterator[Event]`，本次把它在两个端点上暴露出去，并保证 CLI 侧也能走同样的事件协议（TTY 渲染）。

## What Changes

- 新增 `api/routers/chat_stream.py`：
  - `POST /chat/stream` — SSE，`Content-Type: text/event-stream`，事件格式遵循 §5.3。
  - `GET /chat/stream?session_id=...&q=...` — 可选 GET 版本，便于浏览器 `EventSource`（EventSource 不能 POST）。
- 新增 `api/routers/chat_ws.py`：
  - `WebSocket /ws/chat` — 客户端发 `{type:"user_message", session_id, content, use_rag}`；服务端回 `{type:"retrieval|token|done|error"}`；客户端可发 `{type:"abort"}` 提前终止。
- 新增 `api/streaming/` 工具层：
  - `sse.py`：`event_to_sse(event) -> bytes`，正确处理多行、SSE 保活 ping。
  - `protocol.py`：`StreamEvent` TypedDict / Pydantic 联合类型，统一事件 schema（CLI + API 共用）。
  - `abort.py`：`AbortContext`（`asyncio.Event`），供 WS 端中断 `ChatService.generate` 用。
- `core/chat_service.py` 增强：
  - `generate(..., abort: asyncio.Event | None = None)`，内部 `await asyncio.wait` 选择 LLM 输出 vs abort。
- `app/chat_app.py` CLI 侧：
  - CLI 事件消费改为走同一份 `StreamEvent` schema（通过本地 `ChatService` 直连，不走 HTTP），保证 CLI/Web 行为一致。
- 新增 `api/schemas/stream.py`：所有事件的 Pydantic 模型（给 OpenAPI 显示）。

## Non-goals

- 不做 HTTP/2 server push。
- 不做断线重连（resume）与事件 id（`Last-Event-ID`）—— 先做一次性流。
- 不做多客户端广播（一次只服务一个调用方）。
- 不接 Redis pub/sub（Change 8 做 broker 后可再扩）。

## Impact

- **新增**：`api/routers/chat_stream.py`、`api/routers/chat_ws.py`、`api/streaming/{__init__,sse,protocol,abort}.py`、`api/schemas/stream.py`。
- **修改**：`core/chat_service.py`（加 abort 参数）、`api/app.py`（挂 ws 路由）、`app/chat_app.py`（事件消费改走 protocol）。
- **依赖**：`websockets>=12`（uvicorn 已带）、无额外包；`sse-starlette` 可选，本期**不引入**（手写 SSE 以便精确控制）。
- **风险**：中。SSE / WS 的背压、中断语义容易错；必须有端到端测试（httpx SSE + `starlette.testclient` WebSocket）。
- **回退方式**：`git revert`；REST 非流式端点仍可用（Change 6 保留）。
