# Free Deploy Stack

这是当前项目的推荐白嫖部署组合。

## 最佳组合

```text
Frontend websites  -> Vercel Hobby
Backend FastAPI    -> Render Free Docker Web Service
Postgres pgvector  -> Supabase Free 或 Neon Free
Redis              -> Upstash Free
LLM Provider       -> OpenAI-compatible / OpenRouter / Ollama Cloud
```

## 你需要准备的账号

1. GitHub：托管代码。
2. Vercel：部署 `websites/`。
3. Render：部署后端 Docker。
4. Supabase 或 Neon：PostgreSQL + pgvector。
5. Upstash：Redis。
6. OpenAI-compatible provider：聊天和 embedding 模型。

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
3. 创建 Render Backend，配置环境变量，部署 Docker。
4. 确认后端 `/health` 正常。
5. 创建 Vercel Frontend，Root Directory 选 `websites`。
6. 将 Vercel 域名填回后端 `APP_CORS_ORIGINS`。
7. 将 Render 后端 URL 填到 Vercel `RAG_API_URL`。
8. 测试注册、登录、providers、chat、wiki。

## 当前已落地文件

```text
Dockerfile
.dockerignore
deploy/backend/entrypoint.sh
deploy/backend/render.yaml
websites/Dockerfile
websites/.dockerignore
deploy/websites/render.yaml
docs/DEPLOY_BACKEND_DOCKER.md
docs/DEPLOY_WEBSITES.md
```

## 注意事项

- Render Free 会休眠，第一次请求可能冷启动。
- 免费平台不适合跑本地 Ollama 模型。
- RAG embedding 模型必须和数据库向量维度匹配。
- `RAG_EMBED_DIM` 默认是 `768`，如果换 embedding 模型，可能需要迁移数据库 schema。
- 生产环境必须设置非默认 `JWT_SECRET` 和 `PROVIDER_ENCRYPTION_KEY`。
