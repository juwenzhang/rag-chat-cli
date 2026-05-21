# Websites Deploy

`websites/` 是 Next.js App Router SSR 应用，包含 BFF route handlers。它不是纯静态站点，因此不要只上传 `.next` 根目录。

## 推荐方案

### 首选：Vercel Hobby

最省心，Next.js 兼容最好。

配置：

```text
Framework Preset: Next.js
Root Directory: websites
Install Command: pnpm install --frozen-lockfile
Build Command: pnpm build
Output Directory: 留空
```

环境变量：

```bash
RAG_API_URL=https://你的后端服务域名
SESSION_COOKIE_NAME=rag_session
SESSION_COOKIE_SECURE=true
NEXT_PUBLIC_APP_NAME=RAG-AI
```

如果使用自定义域名并需要跨子域 cookie，再设置：

```bash
SESSION_COOKIE_DOMAIN=.example.com
```

### 备选：Docker standalone

已提供：

```text
websites/Dockerfile
websites/.dockerignore
deploy/websites/render.yaml
```

`websites/next.config.ts` 默认不启用 standalone，避免影响 Vercel。Docker 构建时会设置：

```bash
NEXT_OUTPUT_STANDALONE=true
```

然后生成：

```text
.next/standalone/server.js
.next/static
public
```

容器启动：

```bash
node server.js
```

## 本地验证 websites Docker

```bash
cd websites
docker build -t rag-ai-websites .
docker run --rm -p 3000:3000 \
  -e RAG_API_URL=http://host.docker.internal:8000 \
  -e SESSION_COOKIE_NAME=rag_session \
  -e SESSION_COOKIE_SECURE=false \
  rag-ai-websites
```

访问：

```text
http://localhost:3000
```

Linux 上如果 `host.docker.internal` 不可用，可以改为宿主机 IP，或使用 Docker network。

## Render 部署 websites Docker

如果不使用 Vercel，也可以在 Render 创建 Docker Web Service：

```text
Root Directory: websites
Dockerfile Path: ./Dockerfile
Health Check Path: /
Plan: Free
```

环境变量：

```bash
RAG_API_URL=https://你的后端服务域名
SESSION_COOKIE_NAME=rag_session
SESSION_COOKIE_SECURE=true
NEXT_PUBLIC_APP_NAME=RAG-AI
```

也可以参考 `deploy/websites/render.yaml`。

## 与后端的连接

浏览器请求链路：

```text
Browser
  -> Next websites /api/** BFF
  -> RAG_API_URL FastAPI backend
```

所以后端必须允许前端域名：

```bash
APP_CORS_ORIGINS=https://你的前端域名
```

如果 Vercel preview 域名也要访问后端，可以临时配置多个 origin：

```bash
APP_CORS_ORIGINS=https://your-app.vercel.app,https://your-preview.vercel.app
```

## 为什么不直接部署 `.next`

`.next` 是构建产物，不是完整运行包。SSR 运行还需要：

```text
Node runtime
public/
server.js 或 next start
运行时环境变量
```

自托管时请使用 standalone：

```text
.next/standalone
.next/static
public
```

Vercel 部署时则交给 Vercel 原生 Next 构建流程处理。
