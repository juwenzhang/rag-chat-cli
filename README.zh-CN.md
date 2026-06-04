# rag-chat-cli

[![ci](https://github.com/juwenzhang/rag-chat-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/juwenzhang/rag-chat-cli/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)
[![Node](https://img.shields.io/badge/node-20+-green.svg)](clients/tui/package.json)

> 📖 **Language / 语言**：[English](README.md) · **简体中文**

一套可自托管的"和自己的 LLM 聊"全栈方案——本地 Ollama 优先、兼容
OpenAI 协议端点；自带 RAG 检索记忆、ReAct 工具调用，配齐了一套精致的
Web 应用和一套全屏 Ink 终端。

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   Next.js Web  ──┐                            ┌─►  Ollama        │
│                  │                            │                  │
│   Ink TUI    ────┼──►  FastAPI  ──►  Service ─┤                  │
│                  │  (REST + SSE)              │    pgvector RAG  │
│   你的客户端  ───┘                            └─►  MCP 工具       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 目录

- [为什么做这个](#为什么做这个)
- [截图](#截图)
- [关键能力](#关键能力)
- [架构](#架构)
- [快速开始 —— 本地起栈](#快速开始--本地起栈)
- [Ink 终端客户端（`lhx-rag`）](#ink-终端客户端lhx-rag)
- [Web 客户端](#web-客户端)
- [REST / SSE 速查](#rest--sse-速查)
- [配置](#配置)
- [项目结构](#项目结构)
- [文档索引](#文档索引)
- [License](#license)

---

## 为什么做这个

大多数"和你的数据聊天"的 demo，要么是个 notebook、要么是托管 SaaS，
搬到真实工作流就崩。**rag-chat-cli** 把"聊天层"当生产软件来做：

| 关注点 | 我们怎么做 |
| --- | --- |
| **本地优先** | Ollama 是头等公民；OpenAI 协议提供商（vLLM / Groq / OpenRouter…）也支持，但在启动序列里晚一截。 |
| **真持久化** | 会话、消息、记忆、知识库都落 Postgres；向量走 pgvector；后台队列用 Redis。没有任何"内存里的伪存储"。 |
| **两套真客户端** | Next.js Web（RSC + 流式）和 Ink 终端共享同一份 OpenAPI；一个能做的事，另一个也都能做。 |
| **多客户端鉴权** | 单独挂载 `/v1/*` 子 app，靠 `X-Client-Id` 白名单隔离非浏览器流量，反代（HF Spaces、CDN）不会再把 CLI 干掉。详见 [docs/MULTI_CLIENT_AUTH_DESIGN.md](docs/MULTI_CLIENT_AUTH_DESIGN.md)。 |
| **稳定流式协议** | 一套 `Event` 词表（`token`、`thought`、`tool_call`、`tool_result`、`retrieval`、`done`、`error`）跑在 SSE 上，所有客户端按同一规则渲染。详见 [docs/STREAM_PROTOCOL.md](docs/STREAM_PROTOCOL.md)。 |

---

## 截图

### Web —— 首页（已登录，中文）

![Web 首页 · 中文](docs/images/web-home-zh.png)

### Web —— 登录卡片

![Web 登录 · 中文](docs/images/web-login-zh.png)

### Web —— 首页（英文）

![Web 首页 · 英文](docs/images/web-home-en.png)

### 终端 —— 登录

![TUI 登录](docs/images/tui-login.png)

### 终端 —— 三栏对话

![TUI 主界面](docs/images/tui-shell.png)

> 终端客户端 `lhx-rag` 是个全屏 Ink 应用：左边 sessions、中间
> transcript、底部 composer，sidebar 底部常驻 model / provider 信息。

---

## 关键能力

- **ReAct 代理循环**：多步工具调用以 `thought` / `tool_call` /
  `tool_result` 事件回吐，全程被 `ResourceLimits`（`max_steps`、
  单步工具上限、单次调用超时）兜底。
- **两种 LLM 后端，一套协议**：`OllamaClient`（本地）和
  `OpenAIClient`（OpenAI / vLLM / Together / Groq / 任何兼容端点）
  都实现同一个 `LLMClient`，换 provider 不动 `ChatService`。
- **完整的 Provider 管理**：`Provider` 行存每个用户的路由（base
  URL、加密 API key、is_default 等）；两端客户端都能通过同一份
  REST 接口做列表 / 添加 / 测试 / 拉模型 / 删除。
- **混合检索 RAG**：`PgvectorKnowledgeBase` 把向量检索（pgvector）
  和 `pg_trgm` 词法分数做 Reciprocal Rank Fusion，再过一道可插拔
  `Reranker`。引用以 `[N]` 标注，前端/CLI 都能反向定位。
- **MCP 集成**：stdio JSON-RPC 客户端 + `McpTool` 适配器，任何
  [Model Context Protocol](https://modelcontextprotocol.io) 服务
  对代理来说和普通工具没区别。
- **持久化记忆**：会话级 chat history、用户级长期记忆（带
  `FactExtractor` 钩子），自动按上下文窗做历史摘要。
- **全链路流式**：`POST /chat/stream` 的 SSE 事件在两端客户端走同
  一形态；另有支持 abort 的 WebSocket 变体。
- **后台 Worker**：基于 Redis 的 FIFO 队列 + `Worker` 泵，重活
  （ingestion / reindex）出请求链路。
- **客户端鉴权分流**：根路径保持严格（浏览器 CORS 白名单）；
  `/v1/*` 子 app 改用 `X-Client-Id` 白名单。CLI、MCP 服务、你自己
  写的脚本，不再借 Web 的 CORS 政策。
- **可观测**：可选 OpenTelemetry tracer（没装 OTel 时是 no-op），
  以及一个 `UsageAccumulator` 跨 provider 归一化 token / cost。

---

## 架构

```
api/                            FastAPI 应用
   ├─ app.py                    根 app + /v1 子 app + 中间件顺序
   ├─ middleware/               ClientId 白名单、按路径分流的 CORS
   └─ routers/                  REST 端点（auth、chat、knowledge、
                                providers、sessions、shares…）

clients/
   └─ tui/                      Ink（终端版 React） —— `lhx-rag`

websites/                       Next.js 15（RSC）+ Tailwind + Server Actions

service/                        后端领域层
   ├─ chat/                  ChatService + prompts/titles/history/
   │                         tokens/limits
   ├─ llm/                   {Ollama,OpenAI}Client : LLMClient
   ├─ providers/             provider 注册 + 运行时解析
   ├─ knowledge/             PgvectorKnowledgeBase + Reranker + Ingestor
   ├─ memory/                {File,Db}ChatMemory + UserMemoryStore
   ├─ db/                    SQLAlchemy 异步模型 / session 工厂
   ├─ tools/                 ToolRegistry + FunctionTool + McpTool
   ├─ mcp/                   stdio JSON-RPC 客户端 + 适配
   ├─ workers/               Redis 队列 + worker
   ├─ streaming/             Event 词表 + AbortContext
   └─ common/                共享基础设施
```

每个模块都靠 Protocol 解耦。要加一个 Anthropic LLM、一个 Cohere
reranker、一个 Postgres 后端的队列、一个 HTTP MCP transport——都是
单文件改动，碰不到 `ChatService`。

---

## 快速开始 —— 本地起栈

> 前置：**Python ≥ 3.10**、[uv](https://github.com/astral-sh/uv)、
> Docker（拉 Postgres + pgvector + Redis）、跑着的 Ollama *或者*
> 一个 `OPENAI_API_KEY`。可选：**Node ≥ 20**（如果要跑 Web /
> Ink 客户端）。

```bash
# 1. 克隆 + 装后端依赖
git clone https://github.com/juwenzhang/rag-chat-cli
cd rag-chat-cli
uv sync

# 2. 拉你要用的聊天 / 嵌入 / 视觉模型
ollama pull qwen3-coder-next:cloud   # 聊天默认；随便挑
ollama pull nomic-embed-text         # /save、/reflect、RAG 都要它
ollama pull qwen3-vl:235b-cloud      # 图片识别要它

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env：
#   - DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5432/ragdb
#   - JWT_SECRET=<openssl rand -hex 32>
#   - OLLAMA_BASE_URL=http://localhost:11434
#   - APP_ALLOWED_CLIENT_IDS=lhx-rag-cli  （默认已经写好，详见"配置"）

# 4. 起 Postgres + Redis，跑迁移（幂等）
make db.up
make db.migrate

# 5. 起 FastAPI（自动 reload）
make dev.api
# → http://localhost:8000  （根路径走严格 CORS 给 Web 用，
#                          /v1/* 走 X-Client-Id 白名单给非浏览器用）
```

两套客户端任选：

```bash
# Ink 终端 —— 全屏三栏
make dev.cli            # 或 cd clients/tui && pnpm dev

# Next.js 网站
make dev.web            # 或 cd websites && pnpm dev

# 也可以一次性起三个（需要 tmux）
make dev.all
```

---

## Ink 终端客户端（`lhx-rag`）

一个全屏 Ink 应用，只走 FastAPI 的 `/v1` 表面，用 `ink` + `zustand`
+ `marked`（终端 markdown 渲染）搭起来。

### 提供的能力

- **三栏可聚焦**：sessions / transcript / composer，`Tab` 和
  `Shift+Tab` 循环切焦点。
- **斜杠命令** 带模糊补全 + 可滚动候选面板（`/help` 看全部）。
- **侧栏底部** 钉了身份、API 地址、当前 model、当前 provider、
  rag / think 状态——shell prompt 不再骗你"是哪个模型刚回的"。
- **alt-screen 缓冲** —— 退出时恢复 shell 原 scrollback（不想要
  的话设 `LHX_RAG_NO_FULLSCREEN=1`）。
- **跨账号状态隔离** —— `/logout` 会清屏、清 provider 缓存再渲染
  登录卡。

### 斜杠命令（节选）

| 命令 | 说明 |
| --- | --- |
| `/help` | 打开按类分组的命令面板。 |
| `/new [title]`、`/sessions`、`/switch <id\|序号>`、`/title <文本>` | 会话管理。 |
| `/rag on\|off`、`/think on\|off\|low\|medium\|high` | 单轮开关。 |
| `/regenerate`（`/r`）、`/stop`、`/edit <text>`、`/rmsg`、`/eval` | 对话操作。 |
| `/model [<tag>\|set <provider> <tag>\|clear\|show]` | 查看 / 切换当前 session 的模型。直接 `/model` 会同时打印当前 pin **和** provider 上的前 5 个可用 chat 模型 tag。 |
| `/pref [show\|set <key> <值>\|clear <key>]` | 用户级默认：provider、model、embed、rag。 |
| `/kb [list\|add\|rm\|reindex\|search <q>]` | 知识库管理。 |
| `/providers [list\|add\|rm\|default\|test]` | LLM provider 路由。 |
| `/models [list\|pull\|rm]` | 在 provider 上拉 / 删模型。 |
| `/register <email> <password> [name]`、`/whoami`、`/logout` | 账号流。 |
| `/quit`（`/q`） | 退出。 |

详细设计见 [clients/tui/README.md](clients/tui/README.md)
（在该目录跑 `pnpm dev` 即可调试）。

---

## Web 客户端

`websites/` 是 Next.js 15（App Router + RSC）工作区，含三个项目：

```
websites/
   ├─ apps/web/                 面向用户的聊天应用
   ├─ apps/admin/               管理后台
   └─ packages/                 共享 UI / 工具 / 文案
```

亮点：

- **多语言**：中英共用同一份 schema，首页右上角语言切换。
- **流式**：Server Actions 直推 SSE，事件形态和 TUI 一样。
- **知识库 / provider / model 管理**：CLI 那套 REST 的 UI 完整版。
- **组织 / wiki 工作区**：团队共享知识库——TUI 这块还没追上。

部署：
[docs/DEPLOY_WEBSITES.md](docs/DEPLOY_WEBSITES.md)、
[docs/DEPLOY_BACKEND_DOCKER.md](docs/DEPLOY_BACKEND_DOCKER.md)、
[docs/DEPLOY_FREE_STACK.md](docs/DEPLOY_FREE_STACK.md)。

---

## REST / SSE 速查

OpenAPI 自动发布在 `GET /openapi.json`，Swagger UI 在 `GET /docs`。
分组概览：

| 分组 | 端点 |
| --- | --- |
| `auth` | `POST /v1/auth/{register,login,logout,refresh}` |
| `me` | `GET /v1/me`、`PATCH /v1/me`、`GET\|PUT /v1/me/preferences` |
| `chat` | `POST /v1/chat/sessions`、`GET /v1/chat/sessions`、`PATCH\|DELETE /v1/chat/sessions/{id}`、`GET /v1/chat/sessions/{id}/messages`、`POST /v1/chat/messages`、**`POST /v1/chat/stream`**、`POST /v1/chat/stream/regenerate`、`PATCH\|DELETE /v1/chat/messages/{id}`、`GET\|POST /v1/chat/messages/{id}/evaluation` |
| `knowledge` | `POST /v1/knowledge/documents`、`GET /v1/knowledge/documents`、`GET\|PATCH\|DELETE /v1/knowledge/documents/{id}`、`POST /v1/knowledge/documents:reindex`、`GET /v1/knowledge/search` |
| `providers` | `GET\|POST /v1/providers`、`PATCH\|DELETE /v1/providers/{id}`、`GET /v1/providers/{id}/models`、`POST /v1/providers/{id}/models/{meta,pull,delete,show}`、`POST /v1/providers/test` |
| `assets` | `POST /v1/assets/images`、`GET /v1/assets/{id}` |
| `shares / bookmarks / orgs / wikis` | 完整 CRUD —— 见 OpenAPI |

> **浏览器调用方**直接打根路径（不带 `/v1`），走 root CORS 白名单；
> **非浏览器调用方**（Ink TUI、MCP 服务、你自己的脚本）打 `/v1/*`
> 并带上 `X-Client-Id`。Handlers 是同一套，分流只发生在中间件层。

流式事件词表（`token`、`thought`、`tool_call`、`tool_result`、
`retrieval`、`done`、`error`）见
[docs/STREAM_PROTOCOL.md](docs/STREAM_PROTOCOL.md)。

---

## 配置

`.env.example` 是单一事实源——复制成 `.env` 改即可，大部分项有合
理默认。

| 分组 | 变量 | 说明 |
| --- | --- | --- |
| `app` | `APP_ALLOWED_CLIENT_IDS` | 逗号分隔的 `/v1/*` 流量白名单。默认 `lhx-rag-cli`。 |
| `auth` | `JWT_SECRET`、`JWT_*_EXPIRES_MIN` | HS256 access + refresh。 |
| `db` | `DATABASE_URL`、`DB_POOL_SIZE`、`ECHO_SQL` | 异步 asyncpg URL。 |
| `redis` | `REDIS_URL` | Worker 队列 + 缓存。 |
| `ollama` | `OLLAMA_BASE_URL`、`OLLAMA_CHAT_MODEL`、`OLLAMA_EMBED_MODEL`、`OLLAMA_API_KEY`、`OLLAMA_THINK` | 本地 / 托管 Ollama。 |
| `openai` | `OPENAI_BASE_URL`、`OPENAI_CHAT_MODEL`、`OPENAI_EMBED_MODEL`、`OPENAI_API_KEY`、`OPENAI_ORGANIZATION` | OpenAI 协议端点。 |
| `retrieval` | `RAG_ENABLED`、`RAG_TOP_K`、`RAG_MIN_SCORE`、`RAG_EMBED_DIM`、`RAG_IMAGE_CAPTION_MODEL` | RAG 默认值。 |
| `evaluation` | `EVAL_ENABLED`、`EVAL_MODEL` | `/eval` 用的常驻评审。 |
| `rate_limit` | `RATE_LIMIT_PER_MIN` | 单 IP 全局限速。 |

### TUI 专用

`clients/tui/.env` 在构建时打包、在 dev 模式下重读：

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `DEFAULT_BASE_URL` | `http://127.0.0.1:8000` | 打到发布产物里的默认 base URL。 |
| `RAG_API_BASE_URL` | _(未设)_ | 单次启动的临时覆盖，优先级比 `DEFAULT_BASE_URL` 高。 |
| `LHX_RAG_NO_FULLSCREEN` | _(未设)_ | 设为 `1` 跳过 alt-screen（管道输出 / CI 友好）。 |

解析顺序：`options.baseUrl` → `RAG_API_BASE_URL` →
`DEFAULT_BASE_URL` → loopback 兜底。

---

## 项目结构

```
.
├── alembic/                 数据库迁移
├── api/                     FastAPI HTTP / SSE 入口
├── clients/tui/             Ink 终端客户端（`lhx-rag`）
├── deploy/                  Render + HF Space 配方
├── docs/                    架构 / 部署 / 设计文档
│   └── images/              README 截图
├── openspec/                living spec + change proposals
├── service/                 后端领域层
├── websites/                Next.js 工作区（web + admin）
├── settings.py              pydantic-settings + 扁平 → 嵌套映射
├── pyproject.toml
├── docker-compose.yml
├── Dockerfile               后端镜像（HF Space 也用它）
├── README.md                English README
└── README.zh-CN.md          ← 你正在看
```

---

## 文档索引

- [docs/MULTI_CLIENT_AUTH_DESIGN.md](docs/MULTI_CLIENT_AUTH_DESIGN.md) —— `/v1` 为何存在、device-flow 路线图。
- [docs/STREAM_PROTOCOL.md](docs/STREAM_PROTOCOL.md) —— SSE 事件线协议。
- [docs/AUTH_DESIGN.md](docs/AUTH_DESIGN.md) —— JWT access / refresh、密码策略。
- [docs/CHAT_OBSERVABILITY_EVALUATION_VISION.md](docs/CHAT_OBSERVABILITY_EVALUATION_VISION.md) —— 评估 / 视觉链路。
- [docs/OLLAMA_CAPABILITIES_ADAPTATION.md](docs/OLLAMA_CAPABILITIES_ADAPTATION.md) —— 能力探测 + 回退。
- [docs/WEB_SEARCH_CONTEXT_OPTIMIZATION.md](docs/WEB_SEARCH_CONTEXT_OPTIMIZATION.md) —— 工具结果裁剪。
- [docs/FRONTEND_NEXT_OPTIMIZATION.md](docs/FRONTEND_NEXT_OPTIMIZATION.md) —— RSC / 流式经验。
- [docs/FRONTEND_SSR_MVC.md](docs/FRONTEND_SSR_MVC.md) —— Web 端 server-action 布局。
- [docs/DEPLOY_BACKEND_DOCKER.md](docs/DEPLOY_BACKEND_DOCKER.md)、[DEPLOY_WEBSITES.md](docs/DEPLOY_WEBSITES.md)、[DEPLOY_FREE_STACK.md](docs/DEPLOY_FREE_STACK.md) —— 运维指引。
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) —— 本地工具链（uv / alembic / pre-commit）。
- [openspec/](openspec/) —— living spec；当前 `refactor/tui-refactor`
  分支承载 TUI 重写 + 多客户端鉴权 Phase 1。

---

## License

采用 **MIT 协议** 发布。在保留版权与许可声明的前提下，可以自由使
用、修改、再分发。
