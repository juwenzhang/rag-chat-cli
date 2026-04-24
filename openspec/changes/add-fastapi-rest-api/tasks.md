# Tasks: FastAPI REST API Layer

## 1. 依赖

- [ ] 1.1 `pyproject.toml` 新增：`fastapi>=0.111`、`uvicorn[standard]>=0.30`。
- [ ] 1.2 dev 新增：`httpx>=0.27`（已在 ollama 用到可跳过）、`anyio>=4`。
- [ ] 1.3 `uv sync` 成功。

## 2. Settings 扩展

- [ ] 2.1 `settings.app` 补字段：`cors_origins: list[str] = ["*"]`（dev 默认），`host: str = "0.0.0.0"`，`port: int = 8000`。
- [ ] 2.2 `.env.example` 补 `APP__CORS_ORIGINS=http://localhost:5173`。
- [ ] 2.3 prod 模式下 `cors_origins` 为空或含 `*` 时 warning（不强制 raise）。

## 3. 中间件

- [ ] 3.1 新建 `api/middleware/__init__.py`。
- [ ] 3.2 `request_id.py`：`RequestIDMiddleware` + `current_request_id()` ContextVar。
- [ ] 3.3 `logging.py`：`AccessLogMiddleware` 记录 method/path/status/duration/user_id/request_id。
- [ ] 3.4 `errors.py`：`install_exception_handlers(app)` 注册所有 handler，严格按 design 表格映射。
- [ ] 3.5 单测 `tests/unit/api/middleware/test_request_id.py`：响应头 `X-Request-ID` 与请求一致；缺省时服务端生成。

## 4. Common schemas

- [ ] 4.1 `api/schemas/common.py`：`Page[T]`、`ErrorResponse`、`OkResponse`。
- [ ] 4.2 `Page` 泛型在 Pydantic v2 下用 `Generic[T]` 正确工作（验证 `Page[UserOut]` 能序列化）。

## 5. Chat schemas

- [ ] 5.1 `api/schemas/chat.py`：`CreateSessionIn(title?)`、`ChatSessionOut(id, title, created_at)`、`MessageIn(session_id, content, use_rag=False)`、`MessageOut(id, role, content, created_at)`。

## 6. Knowledge schemas

- [ ] 6.1 `api/schemas/knowledge.py`：`DocumentIn(source, title?, content)`、`DocumentOut(id, source, title, created_at)`、`SearchHitOut(document_id, title, snippet, score)`。

## 7. Routers

### 7.1 `routers/auth.py`

- [ ] 7.1.1 实现 `/register`、`/login`、`/refresh`、`/logout` 四个端点。
- [ ] 7.1.2 所有端点都有 `response_model` + `status_code` + `summary`。
- [ ] 7.1.3 `/register` 的 password 通过 `constr(min_length=8)` 校验。

### 7.2 `routers/me.py`

- [ ] 7.2.1 `/me` GET 返回 `UserOut`。
- [ ] 7.2.2 `/me` PATCH 仅允许改 `display_name`（body schema 白名单）。

### 7.3 `routers/chat.py`

- [ ] 7.3.1 `POST /sessions` 创建，写入 `chat_sessions` 表。
- [ ] 7.3.2 `GET /sessions` 分页返回，按 `updated_at desc`。
- [ ] 7.3.3 `GET /sessions/{id}/messages` 分页，必须校验 `session.user_id == user.id`，否则 404（避免枚举）。
- [ ] 7.3.4 `POST /messages` 调用 `ChatService.generate_full(...)`（若 Change 3 只暴露 async iterator，本 change 补一个 `generate_full` 辅助方法——聚合全部 token 事件成完整文本）。

### 7.4 `routers/knowledge.py`

- [ ] 7.4.1 `POST /documents`：写 `documents` 表（chunk/embedding 留给 Change 9）。
- [ ] 7.4.2 `POST /documents:reindex`：本期返回 202 + `OkResponse`，TODO 注释等 workers。
- [ ] 7.4.3 `GET /search`：返回空列表 + `logger.info("search not implemented yet")`。

## 8. `api/app.py`

- [ ] 8.1 `lifespan` 接管 `init_engine` / `dispose_engine`。
- [ ] 8.2 注册所有路由 + 中间件。
- [ ] 8.3 `/health` 端点。
- [ ] 8.4 启用 `GZipMiddleware`（min_size=1024）。
- [ ] 8.5 `create_app()` 接受可选 `settings` 参数，便于测试注入。
- [ ] 8.6 `openapi_tags` 明确列出 auth/chat/knowledge/me/meta 的描述文案。

## 9. CLI `serve` 子命令

- [ ] 9.1 `app/cli.py` 扩展 `serve` 子解析器：`--host / --port / --reload / --workers`。
- [ ] 9.2 `uvicorn.run("api.app:create_app", factory=True, ...)`。
- [ ] 9.3 运行 `python main.py serve --port 8001` 能启动、`curl /health` 返回 200。

## 10. OpenAPI dump

- [ ] 10.1 `scripts/dump_openapi.py` 生成 `docs/openapi.json`。
- [ ] 10.2 CI 中保证 `docs/openapi.json` 与 `create_app().openapi()` 一致（`make openapi-check`，Change 11 接入）。

## 11. 测试

- [ ] 11.1 `tests/api/conftest.py`：`app_client` fixture，用 `httpx.AsyncClient(transport=ASGITransport(app))` + SQLite + 程序化 `alembic upgrade head`。
- [ ] 11.2 `test_health.py`、`test_auth_flow.py`、`test_me.py`、`test_chat_routes.py`、`test_knowledge_routes.py`、`test_errors.py`（见 design）。
- [ ] 11.3 覆盖率：`api/` 目录达到 ≥ 90%（AGENTS.md §12 的门槛）。
- [ ] 11.4 `uv run pytest tests/api -q` 全绿。

## 12. 质量与文档

- [ ] 12.1 `ruff check api/` 无错。
- [ ] 12.2 `mypy --strict api/` 无错。
- [ ] 12.3 `docs/API.md` 重写：列出所有端点、请求/响应示例（可直接从 OpenAPI 里 render）。
- [ ] 12.4 AGENTS.md §19 Change Log 追加 "FastAPI routers + middleware + error mapping"。

## 13. 冒烟

- [ ] 13.1 `python main.py serve --port 8001` 启动，`curl /health` = 200。
- [ ] 13.2 `curl -X POST /auth/register -d '{"email":"a@b.c","password":"12345678"}' -H 'content-type: application/json'` 返回 201。
- [ ] 13.3 `curl -X POST /auth/login ...` 拿到 token；用 `Authorization: Bearer ...` 访问 `/me` 200。
- [ ] 13.4 `/docs` 页面可访问，所有 tag 显示齐全。
- [ ] 13.5 `/openapi.json` 产物与 `docs/openapi.json` 一致。
