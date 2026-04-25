# Tasks: switch-chat-memory-to-db

## 1. Protocol + FileChatMemory rename
- 1.1 `core/memory/chat_memory.py`：加 `ChatMemory` Protocol。
- 1.2 把现有实现类改名 `FileChatMemory`（保留 `from_settings`、所有方法签名不变）。
- 1.3 `__all__` 同时导出 `ChatMemory / FileChatMemory`（DbChatMemory 下一步加）。

## 2. DbChatMemory
- 2.1 同文件内新增 `DbChatMemory` 类，按 design §2 写。
- 2.2 `__all__` 加 `DbChatMemory`。

## 3. ChatService 适配
- 3.1 `core/chat_service.py` 的 `memory` 参数类型注解从 `ChatMemory`（具体类）换成 `ChatMemory`（Protocol）—— 改 import 而已。
- 3.2 冒烟：`uv run mypy --strict core/` 通过。

## 4. Wire up — api 层
- 4.1 `api/deps.py` 加 `get_session_factory()` dep（直接 `return current_session_factory()`）。
- 4.2 `api/chat_service.py`：
  - 新增 `build_chat_service_for_user(user, session_factory) -> ChatService` 用 `DbChatMemory`。
  - 新增 `get_chat_service_for_user = Depends` alias。
  - 保留 `get_chat_service`（file-backed）作为默认 / 测试 fallback。
- 4.3 `api/routers/chat.py`：
  - `post_message` 把 dep 换 `get_chat_service_for_user`；
  - 删掉路由层自己 `session.add(Message(...))` 的代码；
  - 用一次 `SELECT ... ORDER BY created_at DESC LIMIT 1` 拿 assistant 消息返响应。
- 4.4 `api/routers/chat_stream.py` & `chat_ws.py`：
  - dep 换 `get_chat_service_for_user`；
  - 删掉 `_persist_turn(...)` 内部写 DB 的调用（`ChatService` 会自己写）。

## 5. Wire up — CLI
- 5.1 `app/chat_app.py::build_default_chat_service()` 按 design §4.3 改写。
- 5.2 banner 增加 memory 模式标签。

## 6. Tests (lightweight)
- 6.1 `tests/unit/core/test_db_chat_memory.py`：
  - 2 条：roundtrip + cross-user 隔离。
- 6.2 修 `tests/unit/core/test_chat_memory.py`：
  - 导入改 `FileChatMemory`，其他不动。
- 6.3 修 `tests/unit/core/test_chat_service.py`：
  - 导入改 `FileChatMemory`。
- 6.4 修 `tests/api/conftest.py`（若有直接 `ChatMemory(...)` 调用，改 `FileChatMemory`）。
- 6.5 `tests/api/test_chat_routes.py::test_post_message_persists` 若存在，改断言：检查 `messages` 表有两行而不是一行。

## 7. Quality gates
- 7.1 `uv run ruff check .`
- 7.2 `uv run ruff format --check .`
- 7.3 `uv run mypy --strict . --explicit-package-bases`
- 7.4 `uv run pytest -q`
- 7.5 `make ci`

## 8. Smoke
- 8.1 未登录启动 CLI：`python main.py chat` → banner 含 `memory: file (offline)` → `/quit`。
- 8.2 登录后启动 CLI：`/login` → 随便聊一句 → `/quit` → 打开 Web（或 curl `/chat/sessions/{id}/messages`）看到那条消息。
- 8.3 `uv run python scripts/dump_openapi.py` diff 应为空（没改任何 endpoint 契约）。

## 9. Docs
- 9.1 AGENTS.md §19 加 v1.2 条目。
