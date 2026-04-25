# Proposal: Switch ChatMemory from File JSON to DB backend

## Why

P4 (`setup-db-postgres-pgvector-alembic`) 已经建好 `chat_sessions` + `messages` 表；P6 的 `POST /chat/messages` 也已经直接写 DB。**但 `core/memory/chat_memory.py` 仍然是 "1 个会话 = 1 个 JSON 文件" 的 `FileChatMemory`**，后果：

1. **CLI 与 Web 历史不互通** —— Web 发的消息进了 `messages` 表，CLI 的 `ChatService.generate` 读历史却从 `./conversations/*.json` 读。用户登录同一个账号，两端看到的历史是两份。
2. **REST 现在是"双写漂移"** —— `api/routers/chat.py::post_message` 自己 `session.add(Message(...))` 写 DB；同一次请求里 `ChatService.generate_full` 又走 `FileChatMemory.append` 写 JSON。两边永远不一致。
3. **SSE / WS 流式端点更糟** —— `POST /chat/stream` 和 `WS /ws/chat` 只让 `ChatService` 自己持久化（即只写了 JSON），**messages 表里这两条路径的数据根本不会出现**。
4. RAG / 观测 / 后续 Web UI 的 "会话列表 + 历史回放" 全部需要 DB 做 single source of truth。

本 change 把 `ChatMemory` 重构成 Protocol + 两个实现（`FileChatMemory` / `DbChatMemory`），REST / SSE / WS 统一走 `DbChatMemory`，消除双写；CLI 登录后也走 `DbChatMemory`，未登录走 `FileChatMemory` 作为离线 fallback。

## What Changes

- **`core/memory/chat_memory.py`** —— 重构：
  - 新增 `ChatMemory` Protocol（`new_session / get / append / delete_session / list_sessions`）。
  - 现有类改名 `FileChatMemory`（逻辑不动）。
  - 新增 `DbChatMemory`：构造器接 `session_factory: async_sessionmaker` + `user_id: uuid.UUID`；`new_session()` 插入 `chat_sessions` 返回 str(uuid)；`get()` / `append()` 读写 `messages` 表；`delete_session()` 走 ORM `delete` 依赖 FK cascade；`list_sessions()` 按 `updated_at desc` 返回当前 user 的 session ids。
- **`core/chat_service.py`** —— 不动对外 API；把 `ChatMemory` 的具体类型换成 Protocol 后原地兼容。
- **`api/chat_service.py::build_chat_service(user_id=...)`** —— 改签名接 `user_id`；返回绑了 `DbChatMemory` 的 `ChatService`。三个路由侧依赖改为 `Depends(build_chat_service_for_user)`，避免跨用户串流。
- **`api/routers/chat.py::post_message`** —— 移除路由层自己写 `Message` 的代码路径；`ChatService.generate_full` 已经内部 append user/assistant 两条，路由只管用 `result["content"]` 构造响应。
- **`app/chat_app.py`** —— `build_default_chat_service()` 读取本地 token：
  - 有效 token → 建 DB engine + `DbChatMemory`；
  - 无 token / token 过期 → `FileChatMemory`（离线模式），并提示 "offline: run /login to sync with server"。
- **无 alembic migration**（P4 已建好 `chat_sessions` / `messages` 表）。

## Non-goals

- 不做游标分页 / 软删除 / 会话重命名（留给 Web UI 的小 change）。
- 不动 `POST /chat/stream` / `WS /ws/chat` 的行为契约 —— 只是把底层存储从 JSON 换成 DB。
- 不做跨用户共享会话 / 多端光标同步。
- 不改 `ChatService.generate` 的事件协议 §5.3。

## Impact

- **新增**：`core/memory/db_chat_memory.py`（或同文件内加类）；`api/chat_service.py` 增强 `user_id` 路径。
- **修改**：`core/memory/chat_memory.py`、`core/chat_service.py`（签名加 `user_id` 传递）、`api/chat_service.py`、`api/routers/chat.py`、`api/routers/chat_stream.py`、`api/routers/chat_ws.py`、`app/chat_app.py`。
- **依赖**：无新增。
- **风险**：低—中。
  - 现存 `./conversations/*.json` 文件**不自动迁移**（dev 环境产出的脏数据，不值当写迁移）；README 说明 "v1.2+ 起 CLI 登录态走 DB，历史不再与旧 JSON 文件共享"。
  - `DbChatMemory` 的 `get()` 被 `ChatService.generate` 在每一轮调用，必须确保 SQL 走索引（`messages(session_id, created_at)` P4 已建）。
- **回退**：`git revert`。任何 change 10 之后的功能（RAG / web-cli token handoff 等）不会依赖本 change 的具体类名，只依赖 Protocol；回退后用 `FileChatMemory` 继续工作。
