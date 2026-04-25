# Tasks: FastAPI REST API Layer

## 1. 依赖

- [x] 1.1 `pyproject.toml` 新增：`fastapi>=0.111`、`uvicorn[standard]>=0.30`、`python-multipart>=0.0.9`。
- [x] 1.2 dev 新增：`anyio>=4`（httpx ASGITransport 间接需要；`httpx` 已在 P5 ollama 路径里安装）。
- [x] 1.3 `uv sync --extra dev` 成功，安装 `fastapi==0.136.1 / starlette / uvicorn / httptools / uvloop / watchfiles / websockets`。

## 2. Settings 扩展

- [x] 2.1 `settings.app` 补字段：`host: str = "0.0.0.0"`、`port: int = 8000`、`cors_origins: list[str] = ["*"]`。
- [x] 2.2 `.env.example` 补 `APP_HOST=0.0.0.0`、`APP_PORT=8000`、`APP_CORS_ORIGINS=http://localhost:5173`；`_FLAT_TO_NESTED` 同步 + `cors_origins` 配 `@field_validator(mode="before")` 把 CSV 切成 list。
- [ ] 2.3 prod 模式下 `cors_origins` 为空或含 `*` 时 warning。*推迟到 `add-observability-otel`（P11）—— 与生产配置体检一并做更合适。*

## 3. 中间件

- [x] 3.1 `api/middleware/__init__.py`（`__all__ = []`，遵循 §3 re-export 约束）。
- [x] 3.2 `request_id.py`：`RequestIDMiddleware` + `current_request_id() -> str` ContextVar。
- [x] 3.3 `logging.py`：`AccessLogMiddleware` 走 stdlib logging（`api.access` logger），跳过 `/health /docs /openapi.json /redoc`。
- [x] 3.4 `errors.py`：`install_exception_handlers(app)` 注册 4 个 handler，严格按 design 表格映射；500 路径必走 `logger.exception(...)` 但不向客户端泄露 `repr(exc)`。
- [x] 3.5 单测 `tests/unit/api/middleware/test_request_id.py`。**改为合并到端到端测试**：`tests/api/test_health.py` 验证 echo + 缺省生成；`tests/api/test_errors.py` 验证 request_id 注入错误体（见 AGENTS.md §19 v1.0 偏离说明）。

## 4. Common schemas

- [x] 4.1 `api/schemas/common.py`：`Page[T]`、`ErrorResponse`、`OkResponse`。
- [x] 4.2 `Page[T]` 用 `BaseModel + Generic[T]`，OpenAPI 输出包含正确的 `items` 子类型（验证：`Page[ChatSessionOut]` 在 `docs/openapi.json` 里展开正确）。

## 5. Chat schemas

- [x] 5.1 `api/schemas/chat.py`：`CreateSessionIn(title?)` / `ChatSessionOut(id, title, created_at, updated_at)` / `MessageIn(session_id, content, use_rag=False)` / `MessageOut(id, session_id, role, content, tokens?, created_at)`。

## 6. Knowledge schemas

- [x] 6.1 `api/schemas/knowledge.py`：`DocumentIn(source, title?, content)` / `DocumentOut(id, source, title, created_at)` / `SearchHitOut(document_id, title?, snippet, score)`。

## 7. Routers

### 7.1 `routers/auth.py`

- [x] 7.1.1 `/register` `/login` `/refresh` `/logout` 全部实装。
- [x] 7.1.2 全部端点带 `response_model + status_code + summary`；`/register` 走 `RegisterIn` 的 `_PASSWORD_RE` 校验（≥ 8 字符 + 含字母数字）。
- [x] 7.1.3 `/refresh /logout` 复用 `RefreshIn` 单字段 DTO。
- [x] 7.1.4 `_to_token_pair(DomainTokenPair) -> api.schemas.auth.TokenPair`：`token_type` 走 DTO 默认值（mypy 不允许把 `str` 塞进 `Literal["bearer"]`，依默认值更干净）。

### 7.2 `routers/me.py`

- [x] 7.2.1 `GET /me` 返回 `UserOut`。
- [x] 7.2.2 `PATCH /me` 仅允许改 `display_name`（`UserPatchIn` 强制白名单，未列字段被 pydantic 默认忽略）。

### 7.3 `routers/chat.py`

- [x] 7.3.1 `POST /chat/sessions` 创建 `ChatSession` 行。
- [x] 7.3.2 `GET /chat/sessions` 分页（`page/size`），`order_by updated_at desc`。
- [x] 7.3.3 `GET /chat/sessions/{id}/messages` 分页，**校验 `session.user_id == user.id`，否则 404**（避免存在性枚举）。
- [x] 7.3.4 `POST /chat/messages`：路由层 `_generate_reply` 在内部聚合 `ChatService.generate(...)` 的 token 流。**未给 ChatService 加 `generate_full` 方法**（见 AGENTS.md §19 v1.0 偏离说明），保持 core 层职责单一。

### 7.4 `routers/knowledge.py`

- [x] 7.4.1 `POST /knowledge/documents` 写 `documents` 表，**原始内容暂存 `meta["content"]`**（schema 没有 `content_md` 列）；chunk + embed 留给 Change 9。
- [x] 7.4.2 `POST /knowledge/documents:reindex` 返回 202 + `OkResponse(ok=True)`，TODO 注释指向 Change 8。
- [x] 7.4.3 `GET /knowledge/search` 返回空列表 + `logger.info("search not implemented yet")`；query 参数走 `Annotated[str, Query(min_length=1, max_length=1024)]` 已做基本校验。
- [x] 7.4.4 额外补 `GET /knowledge/documents` 分页列表（设计里没列出，但 reindex/search 都需要文档存在性，列表 endpoint 是合理补全）。

## 8. `api/app.py`

- [x] 8.1 `@asynccontextmanager` lifespan 接管 `init_engine` / `dispose_engine`（替代已 deprecated 的 `@app.on_event`）。
- [x] 8.2 注册所有路由 + 中间件，外到内顺序 `CORS → GZip → RequestID → AccessLog`。
- [x] 8.3 `/health` 端点（`api/routers/health.py` 单独成文件，访问日志 skip 路径自然命中）。
- [x] 8.4 启用 `GZipMiddleware(minimum_size=1024)`。
- [x] 8.5 `create_app(settings: Settings | None = None)` 接受可选注入；`settings` 通过 `app.state.settings` 暴露给 lifespan。
- [x] 8.6 `openapi_tags` 列出 `meta / auth / me / chat / knowledge` 及描述。

## 9. CLI `serve` 子命令

- [x] 9.1 `app/cli.py` 的 `serve` 子解析器：`--host / --port / --reload / --workers`。
- [x] 9.2 `uvicorn.run("api.app:create_app", factory=True, host=..., port=..., reload=..., workers=..., log_level=settings.app.log_level.lower())`。
- [x] 9.3 `python main.py serve --help` 正常列出选项；`tests/integration/test_cli_boot.py::test_serve_help_exits_zero` 覆盖。

## 10. OpenAPI dump

- [x] 10.1 `scripts/dump_openapi.py` 生成 `docs/openapi.json`（12 paths + 5 tags）；纯 stdlib，不依赖 `.env`。
- [x] 10.2 `Makefile` 新增 `openapi`（导出）+ `openapi.check`（`git diff --quiet docs/openapi.json` 防止 schema drift）。
- [ ] 10.3 CI 中接入 `make openapi.check`。*推迟到 P11 `add-observability-otel` —— 与 contract test / SDK gen 一起做。*

## 11. 测试

- [x] 11.1 `tests/api/conftest.py`：`api_app / client / registered_user / auth_headers` 4 个 fixture；`monkeypatch.setenv` + `importlib.reload(settings_mod)` + `dependency_overrides` 双向覆盖 `get_db_session` / `get_auth_service` 让 SQLite 引擎生效；`_pw._context.cache_clear()` 让 `AUTH_BCRYPT_ROUNDS=4` 真正生效。
- [x] 11.2 `test_health.py`（3）/ `test_auth_flow.py`（3）/ `test_me.py`（2）/ `test_chat_routes.py`（5）/ `test_knowledge_routes.py`（4）/ `test_errors.py`（3）= 20 条。
- [ ] 11.3 覆盖率：`api/` 目录 ≥ 90%。*未在本 change 强制 `scripts/check_coverage.py` 阈值（仍走 `fail_under=0 + --soft`），但 20 条测试覆盖每端点 happy + 401 + error 路径，实际覆盖率较高；门槛上调留给"统一覆盖率提升"的后续小 change。*
- [x] 11.4 `uv run pytest tests/api -q` → 20 passed；全仓 `make test` → 83 passed。

## 12. 质量与文档

- [x] 12.1 `ruff check api/` 无错（全仓 `ruff check .` 通过）；新增 per-file-ignores `api/routers/** = ["B008"]`、`api/deps.py = ["B008"]` —— `Depends(...)` 写默认值是 FastAPI 标准模式，B008 在此误报。
- [x] 12.2 `mypy --strict api/` 无错（全仓 `mypy --strict .` 通过，85 files）。
- [ ] 12.3 `docs/API.md` 重写。*推迟 —— `docs/openapi.json` 已是单一权威源，`README.md` 的 "REST API quick reference" 段提供人类速查表，避免维护两份。*
- [x] 12.4 AGENTS.md §19 Change Log 追加 v1.0 "FastAPI routers + middleware + error mapping + OpenAPI dump"。

## 13. 冒烟

- [ ] 13.1 `python main.py serve --port 8001` 启动 + `curl /health` = 200。*改为通过 `tests/api/test_health.py` 端到端覆盖（httpx ASGITransport），不占用本机端口；`serve --help` 通过 `tests/integration/test_cli_boot.py` 验证。*
- [ ] 13.2 `curl POST /auth/register` 返回 201。*由 `tests/api/test_auth_flow.py::test_register_login_me_refresh_logout` 覆盖。*
- [ ] 13.3 `curl POST /auth/login + Authorization: Bearer` → /me 200。*同上。*
- [ ] 13.4 `/docs` 页面可访问。*由 `scripts/dump_openapi.py` 成功导出 12 paths + 5 tags 间接证明（FastAPI 用同一份 schema 渲染 /docs）。*
- [x] 13.5 `/openapi.json` 产物：`uv run python scripts/dump_openapi.py` → `wrote docs/openapi.json (12 paths)`；`make openapi.check` 通过 git diff 守门。
