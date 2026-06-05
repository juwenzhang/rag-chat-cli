# Docs Index

按领域分层。新文档落在对应子目录里，根目录只放本索引。

## backend/ — Python 后端 / FastAPI / 协议

- [DEVELOPMENT.md](backend/DEVELOPMENT.md) — 本地工具链（uv / alembic / pre-commit）。
- [SERVICE_LAYOUT.md](backend/SERVICE_LAYOUT.md) — `service/` 模块清单、依赖图、重构分批。
- [STREAM_PROTOCOL.md](backend/STREAM_PROTOCOL.md) — SSE / WS 事件线协议。
- [ERROR_CODES.md](backend/ERROR_CODES.md) — 流式 `error` 事件的 `code` 字典 + UI 建议。
- [AUTH_DESIGN.md](backend/AUTH_DESIGN.md) — JWT access / refresh、密码策略。
- [MULTI_CLIENT_AUTH_DESIGN.md](backend/MULTI_CLIENT_AUTH_DESIGN.md) — `/v1/*` 子 app 与 `X-Client-Id` 白名单。

## ai/ — RAG / 工具策略 / 评测 / 视觉

- [CHAT_OBSERVABILITY_EVALUATION_VISION.md](ai/CHAT_OBSERVABILITY_EVALUATION_VISION.md)
- [WEB_SEARCH_CONTEXT_OPTIMIZATION.md](ai/WEB_SEARCH_CONTEXT_OPTIMIZATION.md)

## ollama/ — Ollama 适配

- [OLLAMA_CAPABILITIES_ADAPTATION.md](ollama/OLLAMA_CAPABILITIES_ADAPTATION.md)

## fe/ — Web 前端（`websites/`）

- [FRONTEND_SSR_MVC.md](fe/FRONTEND_SSR_MVC.md)
- [FRONTEND_NEXT_OPTIMIZATION.md](fe/FRONTEND_NEXT_OPTIMIZATION.md)
- [DEPLOY_WEBSITES.md](fe/DEPLOY_WEBSITES.md)

## tui/ — 终端 UI（`clients/tui/`）

待补。

## engineering/ — 工程化原则与 CR 速查

- [PRINCIPLES.md](engineering/PRINCIPLES.md) — DDD / SOLID / SSOT / MVC vs MVVM / 单向数据流 / code smell 总速查。
- [CODE_REVIEW_CHECKLIST.md](engineering/CODE_REVIEW_CHECKLIST.md) — 本仓库专属 CR 清单（红线 + 后端 + 前端 + 协议 + 安全）。

## ops/ — 部署 / 运维

- [DEPLOY_BACKEND_DOCKER.md](ops/DEPLOY_BACKEND_DOCKER.md)
- [DEPLOY_FREE_STACK.md](ops/DEPLOY_FREE_STACK.md)

## 资产

- `images/` — 截图等。
- `openapi.json` — 自动生成的 OpenAPI 规范（构建产物，不要手动编辑）。
