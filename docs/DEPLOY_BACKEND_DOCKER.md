# Backend Docker Deploy

本文档记录后端 FastAPI 服务的免费/低成本 Docker 部署方案。目标是先在没有自有服务器的情况下跑通 demo，后续如果迁到 VPS / Oracle Cloud / Fly.io，仍复用同一套 `Dockerfile`。

## 推荐免费组合

```text
Backend FastAPI  -> Render Free Web Service 或 Koyeb Free
PostgreSQL       -> Supabase Free 或 Neon Free，需要 pgvector
Redis            -> Upstash Redis Free
LLM Provider     -> OpenAI-compatible / OpenRouter / Ollama Cloud
Frontend         -> Vercel Hobby 或 websites Docker standalone
```

> 不建议在免费容器平台里跑本地 Ollama 模型。模型下载、磁盘、内存、推理算力都不适合白嫖平台。

## 已提供文件

```text
Dockerfile
.dockerignore
deploy/backend/entrypoint.sh
deploy/backend/render.yaml
```

容器启动入口：

```bash
uv run uvicorn api.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}
```

默认启动前会执行：

```bash
uv run alembic upgrade head
```

如需关闭自动迁移，设置：

```bash
RUN_MIGRATIONS=false
```

## Render 部署步骤

1. 打开 `https://render.com`。
2. 连接 GitHub 仓库。
3. 创建 `Web Service`。
4. Runtime 选择 `Docker`。
5. Dockerfile 使用仓库根目录的 `Dockerfile`。
6. Plan 选择 `Free`。
7. Health Check Path 填：

```text
/health
```

也可以使用 `deploy/backend/render.yaml` 作为 Blueprint 模板。

## 必填环境变量

Render/Koyeb/Fly 平台里配置：

```bash
APP_ENV=prod
LOG_LEVEL=INFO
RUN_MIGRATIONS=true

JWT_SECRET=<强随机字符串>
PROVIDER_ENCRYPTION_KEY=<Fernet key>

DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DB
REDIS_URL=rediss://...

APP_CORS_ORIGINS=https://你的前端域名

OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=<你的 key>
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBED_MODEL=text-embedding-3-small
```

如果用 OpenRouter：

```bash
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=<OpenRouter key>
OPENAI_CHAT_MODEL=<模型名>
```

注意：OpenRouter/Groq 等平台不一定提供 embedding。RAG 需要确保 `OPENAI_EMBED_MODEL` 对应 endpoint 可用。

## 生成密钥

JWT secret：

```bash
openssl rand -hex 32
```

Fernet key，无需额外安装 `cryptography`：

```bash
python3 -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

也可以在已安装项目依赖的虚拟环境中使用：

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 生产环境变量模板

参考：

```text
deploy/backend/.env.production.example
```

真实值应填写到部署平台的 Environment Variables / Secrets 页面，不要提交到 Git。

## 数据库

### Supabase

1. 打开 `https://supabase.com`。
2. 创建 project。
3. 在 SQL Editor 执行：

```sql
create extension if not exists vector;
```

4. 复制 Postgres connection string。
5. 改成 SQLAlchemy async URL：

```text
postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DB
```

### Neon

Neon 作为免费 Postgres 时建议使用 **Direct connection**，先避免 pooled/PgBouncer 与 asyncpg prepared statements 的兼容坑。

1. 打开 Neon Console。
2. 进入项目的 Connection Details。
3. 选择 Direct connection。
4. 复制 connection string，例如：

```text
postgresql://USER:PASSWORD@HOST/DB?sslmode=require
```

5. 改成 SQLAlchemy async URL：

```text
postgresql+asyncpg://USER:PASSWORD@HOST/DB?sslmode=require
```

6. 在 Neon SQL Editor 执行：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

## Redis

推荐 Upstash：

1. 打开 `https://upstash.com`。
2. 创建 Redis database。
3. 复制 `REDIS_URL`。
4. 优先使用 TLS URL：

```text
rediss://...
```

## 本地验证 Docker

```bash
docker build -t rag-ai-backend .
docker run --rm -p 8000:8000 \
  --env-file .env \
  -e RUN_MIGRATIONS=false \
  rag-ai-backend
```

访问：

```text
http://localhost:8000/health
```

## 后续重构建议

当前容器入口为了 demo 简化，默认启动前自动迁移。后续生产化建议：

- 将 migration 改成 release command/job。
- 为 worker 单独拆镜像或进程。
- 对 SSE / WebSocket 设置平台超时策略。
- 根据免费平台休眠行为增加前端错误提示和重试。
