# Proposal: Containerize Project with Docker & docker-compose

## Why

AGENTS.md §13 明确要求：

> 部署：`Dockerfile`（多阶段，基于 `python:3.11-slim`）；`docker-compose.yml` 一键起 `api / worker / web / postgres / redis / nginx`。
> 运维：env 通过 `.env` 注入；日志 stdout + JSON；健康检查就绪。

前置 change 已经添加了 postgres (Change 4)、redis (Change 8) service stub，但：
- 没有 api / worker / web 的 Dockerfile。
- 没有 Nginx 反代（SSE / WS 需要特殊配置）。
- 没有 healthcheck / depends_on 依赖图。
- 没有 multi-stage 镜像（体积大）。

本次是 §15 P7 的启动任务，把项目从"能本地跑"升级到"任何人 `docker compose up` 就能跑"。

## What Changes

- 新增 `docker/` 目录：
  - `docker/api.Dockerfile` — 多阶段：builder (uv 安装) → runtime (`python:3.11-slim` + 非 root 用户 + 只读应用目录)。
  - `docker/worker.Dockerfile` — 复用 api 镜像但 entrypoint `python main.py worker`。
  - `docker/web.Dockerfile` — 多阶段 node builder → nginx 托管静态产物（Change 12 才真正有 web 源码，这里先准备好）。
  - `docker/nginx.conf` — SSE/WS 友好配置：`proxy_buffering off`、`proxy_http_version 1.1`、`Upgrade` header。
- 完善 `docker-compose.yml`：
  - `postgres / redis / api / worker / web / nginx` 六服务。
  - `profiles: db / web / full`，支持局部启动。
  - `depends_on` 带 `condition: service_healthy`。
  - 统一 `env_file: .env`。
  - 命名 volumes：`pg_data / redis_data`。
  - network `ragnet`（bridge）。
- 新增 `docker-compose.override.yml`（dev 专用，gitignore-safe 示例）：
  - `api` 挂源码、`uvicorn --reload`。
  - `web` 改为 `npm run dev` 的端口映射。
- `.dockerignore`：排除 `.git / __pycache__ / tests / docs / web/node_modules` 等。
- `Makefile`（Change 11 会扩充）本 change 先加 `up / down / logs / rebuild / ps` 五个目标的占位（Change 11 统一完善）。
- 文档 `docs/DEPLOY.md`：本地启动、切 prod、常见故障排查。
- 所有服务加 healthcheck：
  - postgres：`pg_isready`。
  - redis：`redis-cli ping`。
  - api：`curl -f http://localhost:8000/health`。
  - worker：arq 自带的 `health_check_interval` → 写 `/tmp/worker.ok`，`test: ["CMD", "test", "-f", "/tmp/worker.ok"]`。
  - nginx：`wget -q --spider http://localhost/`。

## Non-goals

- 不做 k8s manifests / helm chart。
- 不做 TLS（Nginx 明文 80，用户自己外接）。
- 不做日志收集（Loki / ELK）。
- 不做多阶段 GPU 镜像（Ollama 不在 compose 里托管）。

## Impact

- **新增**：`docker/*.Dockerfile`、`docker/nginx.conf`、`docker-compose.override.yml`、`.dockerignore`、`docs/DEPLOY.md`。
- **修改**：`docker-compose.yml`（大改）、`Makefile`（少量占位）、`README.md`（加 compose 一键指令）。
- **依赖**：无 Python 依赖新增。
- **风险**：中。Dockerfile 写错会导致 CI / 其他用户跑不起来；必须验证 `docker compose up --build` 真的能跑完启动健康检查。
- **回退方式**：`git revert`；本地仍可 `uv run python main.py` 直接启动。
