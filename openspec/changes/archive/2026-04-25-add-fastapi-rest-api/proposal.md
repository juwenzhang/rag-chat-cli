# Proposal: Add FastAPI REST API Layer

## Why

AGENTS.md §5.1 定义了完整的 REST 路由清单：

> `POST /auth/register`、`POST /auth/login`、`POST /auth/refresh`、`POST /auth/logout`
> `GET /me`、`PATCH /me`
> `POST /chat/sessions`、`GET /chat/sessions`、`GET /chat/sessions/{id}/messages`
> `POST /chat/messages` 与 `POST /chat/stream`（后者 Change 7 做）
> `POST /knowledge/documents`、`POST /knowledge/documents:reindex`、`GET /knowledge/search`

§2 约束了 `api/` 的目录结构；§15 P5 要求：在 P4（DB）+ JWT 之后，立刻暴露 REST 以支撑 Web 端（Change 12~14）。

当前 Change 5 已经把 `api/deps.py` 和 `api/schemas/auth.py` 建好，但**还没有任何路由和 FastAPI app 实例**。本次补齐。

## What Changes

- 新增 `api/app.py`：`create_app()` 工厂，装配中间件（CORS / 请求 ID / 日志 / 全局异常 handler）+ 路由。
- 新增 `api/routers/`：
  - `auth.py` — register / login / refresh / logout / me。
  - `chat.py` — sessions CRUD + messages（**仅非流式**，stream 走 Change 7）。
  - `knowledge.py` — documents 上传 / reindex / search（search 的召回接 Change 9 提供的 `retriever`，本次先返回 501 或空列表）。
- 新增 `api/schemas/`：
  - `common.py`（`Page`、`ErrorResponse`、`OkResponse`）。
  - `chat.py`（`ChatSessionOut`、`MessageIn`、`MessageOut`）。
  - `knowledge.py`（`DocumentIn/Out`、`SearchHitOut`）。
- 新增 `api/middleware/`：
  - `request_id.py`（读/生成 `X-Request-ID`，注入 context var）。
  - `logging.py`（结构化 access log：method path status dur_ms user_id）。
  - `errors.py`（全局 handler：`AuthError → 401/409`、`pydantic.ValidationError → 422`、`DomainError → 400`、兜底 `500`）。
- `app/cli.py` 的 `serve` 子命令**实装**：`uvicorn api.app:create_app --factory --host 0.0.0.0 --port 8000`。
- 新增 OpenAPI 自动生成校验：启动时 `dump` 到 `docs/openapi.json`，便于 Web 端 codegen。
- 所有路由都挂 `Depends(get_current_user)` 除了 `/auth/*` 和 `/health`。

## Non-goals

- 不实现 `/chat/stream`（SSE）和 WebSocket（Change 7 做）。
- 不实现 `/knowledge/search` 的真实向量召回（Change 9 做，本次返回空结果 + 日志提示）。
- 不做 rate limit（§10，Change 8 的 Redis 到位后做）。
- 不生成前端 SDK（Change 12 之后再考虑）。

## Impact

- **新增**：`api/app.py`、`api/routers/*.py`、`api/schemas/*.py`、`api/middleware/*.py`、`docs/openapi.json`（生成物）。
- **修改**：`app/cli.py`（`serve` 实装）、`pyproject.toml`（依赖）。
- **依赖新增**：`fastapi>=0.111`、`uvicorn[standard]>=0.30`、`httpx>=0.27`（测试用）。
- **风险**：中。首次引入 HTTP server；必须有 `httpx.AsyncClient + ASGITransport` 的集成测试覆盖每个路由。
- **回退方式**：`git revert`；`serve` 子命令返回 "not implemented"。
