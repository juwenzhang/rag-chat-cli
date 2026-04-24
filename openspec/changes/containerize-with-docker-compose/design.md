# Design: Containerize with Docker & docker-compose

## Context

AGENTS.md §13 明确目标："一个人 clone + cp .env.example .env + docker compose up 即能跑全栈"。同时 §5 流式、§6 auth、§4 DB 都要求 prod 环境下的 HTTPS/反代兼容（SSE `proxy_buffering off` 必须）。

## Goals / Non-Goals

**Goals**
- **可复现**：镜像锁定 base、uv lock + `--frozen` 安装。
- **小体积**：builder / runtime 分离，runtime 不含 uv / 编译工具链。
- **安全**：runtime 用非 root 用户，应用目录 `chown:root:app, chmod=0755`，只读。
- **正确代理 SSE/WS**：Nginx location 级别关闭 buffering，开启 `http_version 1.1` + `Upgrade`。
- **分 profile 启动**：`db` 仅 DB；`web` 为全栈；`full` 包含 nginx + web。

**Non-Goals**
- 不做 TLS 终结（留给用户的外部 LB / Cloudflare）。
- 不做 CI 推镜像到 registry（Change 11 做）。

## Architecture

### Dockerfile：`docker/api.Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1.7
ARG PY_VER=3.11

FROM python:${PY_VER}-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl \
  && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /build
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

FROM python:${PY_VER}-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    APP_HOME=/app
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app
WORKDIR /app
COPY --from=builder --chown=app:app /build /app
# healthcheck 需要 curl
RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/*
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["python", "main.py", "serve", "--host", "0.0.0.0", "--port", "8000"]
```

### Dockerfile：`docker/worker.Dockerfile`

```dockerfile
# 复用 api 的 builder/runtime，仅 CMD 不同
# 为共享镜像，build arg 决定 entrypoint：
FROM api-runtime AS worker
CMD ["python", "main.py", "worker"]
```

> 实际写法：在 compose 里 `image: ragchat-api:${TAG}`，service `worker` 用同一 image + `command: python main.py worker`，**不单独构建**。

### Dockerfile：`docker/web.Dockerfile`（Change 12 落源码后真正使用）

```dockerfile
FROM node:20-alpine AS web-builder
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml* ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY web/ .
RUN pnpm build

FROM nginx:1.27-alpine AS web-runtime
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=web-builder /web/dist /usr/share/nginx/html
HEALTHCHECK --interval=10s --timeout=3s CMD wget -q --spider http://localhost/ || exit 1
```

### `docker/nginx.conf` 关键片段

```nginx
upstream api_upstream { server api:8000; }

server {
    listen 80;
    server_name _;

    # 静态 Web
    root /usr/share/nginx/html;
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API（普通 REST）
    location /api/ {
        proxy_pass http://api_upstream/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # SSE：关 buffering + 明确 http/1.1
    location /api/chat/stream {
        proxy_pass http://api_upstream/chat/stream;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        chunked_transfer_encoding on;
    }

    # WebSocket
    location /api/ws/ {
        proxy_pass http://api_upstream/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}
```

### `docker-compose.yml`

```yaml
name: rag-chat
x-env: &default-env
  env_file: .env

services:
  postgres:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-rag}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-rag}
      POSTGRES_DB: ${POSTGRES_DB:-ragdb}
    volumes: [pg_data:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "${POSTGRES_USER:-rag}"]
      interval: 10s
      timeout: 3s
      retries: 10
    networks: [ragnet]
    profiles: ["db", "web", "full"]

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes: [redis_data:/data]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 10
    networks: [ragnet]
    profiles: ["web", "full"]

  api:
    build: { context: ., dockerfile: docker/api.Dockerfile }
    image: ragchat-api:${TAG:-latest}
    <<: *default-env
    depends_on:
      postgres: { condition: service_healthy }
      redis:    { condition: service_healthy }
    ports: ["8000:8000"]
    networks: [ragnet]
    profiles: ["web", "full"]

  worker:
    image: ragchat-api:${TAG:-latest}
    <<: *default-env
    command: ["python", "main.py", "worker"]
    depends_on:
      postgres: { condition: service_healthy }
      redis:    { condition: service_healthy }
    networks: [ragnet]
    profiles: ["web", "full"]

  web:
    build: { context: ., dockerfile: docker/web.Dockerfile }
    image: ragchat-web:${TAG:-latest}
    depends_on:
      api: { condition: service_healthy }
    networks: [ragnet]
    profiles: ["full"]

  nginx:
    image: nginx:1.27-alpine   # 若 web 镜像自带 nginx 也可省略
    # 仅当 web 镜像不含 nginx 时使用；本 change 默认 web 镜像含 nginx → 省略独立 nginx service
    profiles: ["full-nginx"]

volumes:
  pg_data:
  redis_data:

networks:
  ragnet:
    driver: bridge
```

> 注：我们选择 "web 镜像自带 nginx 托管静态 + 反代 /api/" 的方案，无需独立 nginx service。

### `docker-compose.override.yml` (dev)

```yaml
services:
  api:
    volumes: [".:/app:ro"]    # 源码 bind mount
    command: ["python", "main.py", "serve", "--host", "0.0.0.0", "--port", "8000", "--reload"]
  worker:
    volumes: [".:/app:ro"]
```

### `.dockerignore`

```
.git
.gitignore
.venv
__pycache__
*.pyc
*.log
tests
docs
.idea
.vscode
node_modules
web/dist
conversations
knowledge/*.bak
```

### 运行姿势

```bash
cp .env.example .env
# 仅 DB
docker compose --profile db up -d
# Web 后端栈
docker compose --profile web up -d
# 含前端
docker compose --profile full up -d --build
```

## Alternatives Considered

- **独立 nginx service**：更灵活；本期为简化合并进 web 镜像。后续 TLS / 前端独立部署再拆。
- **distroless runtime**：体积更小但无 curl 难做 healthcheck；slim + curl 是合理平衡。
- **alpine base**：wheel 兼容性差（musl），`asyncpg` 编译坑；选 slim。

## Risks & Mitigations

- **风险**：`uv sync --frozen` 在未生成 `uv.lock` 时失败。
  **缓解**：Dockerfile `COPY uv.lock*`，lock 不存在时也不报错；CI 强制 `uv lock` 后再构建。
- **风险**：dev override 默认挂源码 → prod 误用会把宿主机代码挂进容器。
  **缓解**：文档明确 "override 仅 dev；prod 用 `-f docker-compose.yml` 不加 override"。
- **风险**：Nginx SSE 配置错误导致前端永远收不到数据。
  **缓解**：专门 `tests/smoke/test_sse_through_nginx.sh` 脚本，CI 中 Change 11 接入。

## Testing Strategy

- 构建验证：
  - `docker build -f docker/api.Dockerfile -t ragchat-api:test .` 成功。
  - `docker run --rm ragchat-api:test python -c "import core, api, db"` 成功。
- 组合验证：
  - `docker compose --profile web up -d --build` 后：
    - `curl http://localhost:8000/health` = 200。
    - `docker compose ps` 全部 `(healthy)`。
  - `docker compose --profile full up -d --build`：
    - `curl http://localhost/` 返回前端 index（Change 12 之后真实起效；本 change 以占位 index.html 校验反代正常）。
- 冒烟脚本 `scripts/smoke_compose.sh`：
  - 起 compose → 等 60s healthy → curl 若干端点 → 关。
