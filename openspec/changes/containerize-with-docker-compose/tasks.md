# Tasks: Containerize with Docker & docker-compose

## 1. `.dockerignore`

- [ ] 1.1 新建 `.dockerignore`，按 design 列表排除。
- [ ] 1.2 验证 `docker build` 的上下文大小 < 20 MB（`docker build --progress=plain`）。

## 2. api.Dockerfile

- [ ] 2.1 新建 `docker/api.Dockerfile`（多阶段）。
- [ ] 2.2 builder 阶段：`uv sync --frozen --no-dev`。
- [ ] 2.3 runtime 阶段：`python:3.11-slim` + 非 root `app` 用户 + `curl`。
- [ ] 2.4 `HEALTHCHECK` 正确（含 `--start-period`）。
- [ ] 2.5 `docker build -f docker/api.Dockerfile -t ragchat-api:local .` 成功，镜像大小 < 400MB。
- [ ] 2.6 `docker run --rm ragchat-api:local python -c "from api.app import create_app; print('ok')"` 成功。

## 3. web.Dockerfile（占位）

- [ ] 3.1 新建 `docker/web.Dockerfile`。
- [ ] 3.2 web-builder 阶段：node:20-alpine + pnpm（Change 12 真正用到；本 change 允许 `web/` 暂不存在时降级）。
- [ ] 3.3 web-runtime 阶段：nginx:1.27-alpine + copy `nginx.conf`。
- [ ] 3.4 若 `web/` 不存在，提供一个 `docker/placeholder-index.html`：`<h1>rag-chat (web pending)</h1>`。
- [ ] 3.5 Dockerfile 开头用 ARG 区分 `WITH_WEB=1/0`，为 0 时 COPY placeholder。

## 4. Nginx 配置

- [ ] 4.1 新建 `docker/nginx.conf`（`server { ... }` 只有一个 server block）。
- [ ] 4.2 `/api/` 普通反代。
- [ ] 4.3 `/api/chat/stream` 关 buffering。
- [ ] 4.4 `/api/ws/` WS upgrade。
- [ ] 4.5 `try_files $uri /index.html` 支持 SPA。
- [ ] 4.6 `gzip on` + 常见 mime types。
- [ ] 4.7 `nginx -t -c $(pwd)/docker/nginx.conf` 在容器内校验通过（或 `docker run --rm -v $(pwd)/docker/nginx.conf:/etc/nginx/conf.d/default.conf nginx:1.27-alpine nginx -t`）。

## 5. docker-compose.yml

- [ ] 5.1 重写为 design 列出的结构（name/x-env/services/volumes/networks）。
- [ ] 5.2 `postgres` 服务配置 env + healthcheck + volume。
- [ ] 5.3 `redis` 服务配置 + healthcheck。
- [ ] 5.4 `api` 服务 `depends_on` 使用 `condition: service_healthy`。
- [ ] 5.5 `worker` 服务复用 `api` 镜像 + 改 command。
- [ ] 5.6 `web` 服务 profile `full`。
- [ ] 5.7 三个 profile：`db / web / full` 覆盖全部使用场景。
- [ ] 5.8 `docker compose config` 解析通过（YAML + schema 无错）。

## 6. docker-compose.override.yml

- [ ] 6.1 新建文件，默认 dev 场景：api / worker bind mount `.:/app:ro` + reload。
- [ ] 6.2 文档 `docs/DEPLOY.md` 告诉用户 prod 如何禁用 override（`-f docker-compose.yml`）。

## 7. 环境变量与 .env

- [ ] 7.1 `.env.example` 补齐 `POSTGRES_USER/PASSWORD/DB`、`TAG=latest`、`DB__DATABASE_URL=postgresql+asyncpg://rag:rag@postgres:5432/ragdb`、`REDIS__URL=redis://redis:6379/0`。
- [ ] 7.2 `README.md` 加说明：`cp .env.example .env` 后再 `docker compose up`。

## 8. Makefile 占位

- [ ] 8.1 新增 `make up` / `make down` / `make logs` / `make rebuild` / `make ps`。
  ```make
  up: ; docker compose --profile web up -d
  down: ; docker compose down
  logs: ; docker compose logs -f --tail=100
  rebuild: ; docker compose build --no-cache
  ps: ; docker compose ps
  ```
- [ ] 8.2 Change 11 将在此基础上加 lint/test/coverage 等。

## 9. 启动脚本（迁移 migrations）

- [ ] 9.1 api 容器启动时先跑 `alembic upgrade head`：
  - 方式 A：`CMD ["sh","-c","alembic upgrade head && python main.py serve ..."]`。
  - 方式 B：单独 `migrate` 一次性 service，`depends_on` 让 api/worker 等它完成。
  - **选 B**（更清晰）：新增 `migrate` service（no restart、profile web/full），api/worker `depends_on: migrate: service_completed_successfully`。
- [ ] 9.2 `docker/migrate.Dockerfile` 或复用 api 镜像：`command: ["alembic","upgrade","head"]`。
- [ ] 9.3 冒烟验证：首次 up 自动完成 DDL。

## 10. 健康检查打磨

- [ ] 10.1 api `/health` 返回 db/redis 细粒度状态（Change 8 已做）；compose 只看 overall 200 即可。
- [ ] 10.2 worker 容器没有 HTTP 端口；用 `python main.py worker --heartbeat-file /tmp/worker.ok`（在 `app/cli.py` 增加参数，定时 touch 文件）。
- [ ] 10.3 compose 中 worker `healthcheck: test ["CMD","test","-f","/tmp/worker.ok"]`。

## 11. 测试

- [ ] 11.1 `scripts/smoke_compose.sh`：
  - `docker compose --profile web up -d --build`。
  - `timeout 120 sh -c 'until curl -fsS http://localhost:8000/health; do sleep 2; done'`。
  - `docker compose ps --format json` 解析全部 state=running、health=healthy。
  - `docker compose down -v` 清理。
- [ ] 11.2 `scripts/smoke_sse_through_nginx.sh`（full profile）：`curl -N http://localhost/api/chat/stream ...` 能收到事件。
- [ ] 11.3 文档化手工跑法；CI 接入在 Change 11 做。

## 12. 文档

- [ ] 12.1 新建 `docs/DEPLOY.md`：
  - 最小启动 3 步。
  - profile 介绍。
  - 常见故障：DB 连不上、migrate 失败、SSE 断流、WS 握手 403。
  - 如何查日志 / 备份 pg_data。
- [ ] 12.2 README 加一节"Quick start with Docker"。
- [ ] 12.3 AGENTS.md §19 追加 "Containerization"。

## 13. 冒烟

- [ ] 13.1 `docker compose --profile db up -d` → `docker compose ps` 显示 postgres `(healthy)`。
- [ ] 13.2 `docker compose --profile web up -d --build` → 5 分钟内 api + worker + postgres + redis 全 healthy。
- [ ] 13.3 `curl http://localhost:8000/health` = 200 `{db:ok, redis:ok}`。
- [ ] 13.4 `docker compose --profile full up -d` 启动后 `curl http://localhost/` 返回（占位）index.html。
- [ ] 13.5 `docker compose down -v` 干净退出，volumes 被删除。
