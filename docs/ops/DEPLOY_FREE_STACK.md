# Free Deploy Stack

这是当前项目的推荐白嫖部署组合。

## 最佳组合

```text
Frontend websites  -> Vercel Hobby
Backend FastAPI    -> Render Free Docker Web Service
Object Storage     -> MinIO Space / S3-compatible storage
Postgres pgvector  -> Supabase Free 或 Neon Free
Redis              -> Upstash Free
LLM Provider       -> OpenAI-compatible / OpenRouter / Ollama Cloud
```

## 你需要准备的账号

1. GitHub：托管代码。
2. Vercel：部署 `websites/`。
3. Render：部署后端 Docker。
4. Hugging Face Space 或其他 Docker 平台：部署 MinIO 对象存储。
5. Supabase 或 Neon：PostgreSQL + pgvector。
6. Upstash：Redis。
7. OpenAI-compatible provider：聊天和 embedding 模型。

## 你需要提供给部署配置的值

不要把密钥发到聊天里，直接填到平台环境变量。

### Backend / Render

```bash
JWT_SECRET=<openssl rand -hex 32>
PROVIDER_ENCRYPTION_KEY=<Fernet.generate_key()>
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=rediss://...
APP_CORS_ORIGINS=https://你的 Vercel 域名
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=<key>
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBED_MODEL=text-embedding-3-small
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://你的-minio-api
S3_PUBLIC_ENDPOINT_URL=https://你的-minio-api
S3_ACCESS_KEY=<MinIO access key>
S3_SECRET_KEY=<MinIO secret key>
S3_BUCKET=rag-assets
S3_REGION=us-east-1
```

部署完成后拿到：

```text
https://你的后端.onrender.com
```

### Frontend / Vercel

```bash
RAG_API_URL=https://你的后端.onrender.com
SESSION_COOKIE_NAME=rag_session
SESSION_COOKIE_SECURE=true
NEXT_PUBLIC_APP_NAME=RAG-AI
```

## 推荐部署顺序

1. 创建 Supabase/Neon 数据库，启用 `vector` extension。
2. 创建 Upstash Redis。
3. 创建 MinIO Space，配置 `MINIO_ROOT_USER`、`MINIO_ROOT_PASSWORD`、`MINIO_DEFAULT_BUCKETS=rag-assets`。
4. 创建 Render Backend，配置数据库、Redis、LLM 和 `S3_*` 环境变量，部署 Docker。
5. 确认后端 `/health` 正常。
6. 创建 Vercel Frontend，Root Directory 选 `websites`。
7. 将 Vercel 域名填回后端 `APP_CORS_ORIGINS`。
8. 将 Render 后端 URL 填到 Vercel `RAG_API_URL`。
9. 测试注册、登录、providers、chat、wiki、图片上传。

## 当前已落地文件

```text
Dockerfile
.dockerignore
.github/workflows/deploy-hf-backend.yml
.github/workflows/deploy-hf-minio.yml
deploy/backend/entrypoint.sh
deploy/backend/render.yaml
websites/Dockerfile
websites/.dockerignore
deploy/websites/render.yaml
docs/ops/DEPLOY_BACKEND_DOCKER.md
docs/fe/DEPLOY_WEBSITES.md
minio/Dockerfile
minio/start.sh
minio/README.md
scripts/deploy-hf-minio.sh
```

## 自动部署

后端 / Ollama / MinIO Hugging Face Space 已配置 GitHub Actions 同步：

```text
push/merge 到 master -> GitHub Actions -> push 到 HF Space main -> Space 自动 Docker 构建
```

MinIO workflow 默认推送到 `luhanxin/hf-luhanxin-minio`；如名称后续变化，修改 `.github/workflows/deploy-hf-minio.yml` 的 `HF_MINIO_SPACE` 即可。

需要在 GitHub 配置：

```text
HF_TOKEN=<Hugging Face write token>
```

## 注意事项

- Render Free 会休眠，第一次请求可能冷启动。
- 免费平台不适合跑本地 Ollama 模型。
- RAG embedding 模型必须和数据库向量维度匹配。
- `RAG_EMBED_DIM` 默认是 `768`，如果换 embedding 模型，可能需要迁移数据库 schema。
- 生产环境必须设置非默认 `JWT_SECRET` 和 `PROVIDER_ENCRYPTION_KEY`。
- 生产环境必须设置强随机 `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`，并让后端 `S3_ACCESS_KEY` / `S3_SECRET_KEY` 与其一致。
- 后端上传图片会先在 CPU 上统一转换为 WebP，再写入 MinIO；当前最大上传原图大小为 8 MiB，WebP 最大边长为 2048px。
