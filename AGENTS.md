# AGENTS.md

> 本文件是给 **AI coding agents**（Claude Code / Codex / Cursor / CodeBuddy 等）与**新加入的工程师**阅读的**项目操作手册**。
> 它描述了**目标架构、边界、约定、红线和常见工作流**。
> 正文中文、代码/术语/路径英文。
> 若本文件与代码冲突，**以本文件为准**，应通过 PR 让代码对齐本文件，而不是反过来。

---

## 1. Project Overview

一个基于本地 **Ollama** 的技术博客 AI 助手，目标形态是：

- **CLI 模式**：opencode 风格的交互式终端聊天（rich + prompt_toolkit）。
- **Web 模式**：FastAPI 提供 REST + WebSocket，供未来 Vue3 前端接入。
- **知识增强**：本地 RAG（pgvector）检索项目自有 `knowledge/` 文章并注入 prompt。
- **微调能力**：基于 `peft` 的 LoRA 训练，离线执行。
- **鉴权**：Web 邮箱登录签发 JWT，CLI 与第三方 REST 调用均须携带 token。

**Tech Stack（冻结清单）**

| Layer | Choice | Why (决策理由) |
|---|---|---|
| Language | Python 3.10+ | 已有代码库 |
| Package Mgr | **uv** | 已在用，比 pip/poetry 快 |
| Web | **FastAPI** + uvicorn[standard] | async 原生、OpenAPI 免费、SSE/WS 都很轻 |
| Async DB | **SQLAlchemy 2.x (async)** + asyncpg | 官方推荐、类型友好 |
| RDB | **PostgreSQL 16** (image: `pgvector/pgvector:pg16`) | 关系 + 向量库二合一，16GB 机器只起一个进程 |
| Vector | **pgvector** | 免额外服务；Chroma/Qdrant 常驻 300MB+，省下来 |
| Migrations | **Alembic** | SQLAlchemy 生态事实标准 |
| Cache/MQ | **Redis 7** (alpine, ~10MB RSS) | 缓存、pub/sub（多副本 WS 广播）、限流、ARQ broker |
| Task Queue | **ARQ** | Redis 原生、纯 asyncio、无 Celery 的 broker/beat 复杂度 |
| Embedding | **Ollama `nomic-embed-text`** (~274MB, CPU OK) | 不再引入 sentence-transformers + torch 运行时 |
| LLM | **Ollama** `qwen2.5:1.5b`（默认）| 已在用；1.5B 模型 CPU 可跑 |
| Auth | **JWT (HS256)** via `python-jose` + `passlib[bcrypt]` | 无状态、CLI/Web 通用 |
| CLI UI | **rich** + **prompt_toolkit** | 已有 rich；prompt_toolkit 给多行输入、历史、快捷键 |
| Streaming | **SSE**（REST 单轮） + **WebSocket**（长会话） | 见 §9 决策表 |
| Logging | stdlib logging + 现有 `ColoredFormatter` | 已经好用，不换 |
| Lint/Format | **ruff** + **ruff format** | 一把梭，替代 black/isort/flake8 |
| Types | **mypy**（strict on `api/`、`core/`、`db/`）| 业务代码要类型安全；`scripts/`、`utils/` 宽松 |
| Tests | **pytest** + **pytest-asyncio** + **httpx.AsyncClient** | FastAPI 推荐组合 |

**Web (身份平台 / 业务前端)**

| Layer | Choice | Why |
|---|---|---|
| Framework | **Vue 3** + Vite | 未来 Vue3 业务页共用一套技术栈 |
| Language | **TypeScript (strict)** | — |
| Pkg Mgr | **pnpm ≥ 9** | 磁盘省、安装快 |
| State | **Pinia** | Vue 官方推荐 |
| Router | **Vue Router** | — |
| i18n | **vue-i18n** | 中英双语（见 §11b） |
| HTTP | **Axios** + 统一拦截器（`api/http.ts`） | 401 自动 refresh |
| Form | **VeeValidate + zod** | 类型友好 |
| CSS | **UnoCSS** + **Less** + **CSS Modules** 三层组合 | 分工见 §11b |
| UnoCSS preset | `preset-uno` + `preset-attributify` + `preset-icons`(lucide) | 原子类 + 属性化 + iconify |
| UI 组件 | **Element Plus**（强制二次封装） | 页面禁止直接 import，见 §11b |
| Mock | **msw** | 前端独立可演示 |
| Lint | ESLint flat + Prettier + Stylelint(less) | — |
| Test | Vitest + @vue/test-utils | — |

**Hardware Budget：** 开发机 16GB 内存。容器总占用目标 ≤ 4GB（不含 Ollama 模型权重）。任何选型若常驻内存 > 300MB，须在本文档显式写出理由。

---

## 2. Repository Layout (Target)

> ★ = 本次重构新增；其余为现有或搬迁。
> 过渡期允许新旧路径共存，但**新代码必须写在新路径**，见 §15 迁移策略。

```
test_code/
├── app/                          # ★ 应用入口与编排
│   ├── cli.py                    #   argparse 子命令: chat / serve / train / ingest
│   ├── chat_app.py               #   交互式会话编排 (原 main.run_interactive_chat)
│   └── server.py                 #   FastAPI create_app() 工厂
│
├── api/                          # ★ HTTP / WebSocket 层（只做编排，不放业务）
│   ├── deps.py                   #   DI: db session / redis / current_user(JWT)
│   ├── middleware.py             #   request-id / CORS / access log
│   ├── errors.py                 #   统一异常 → HTTP 响应
│   ├── schemas/                  #   Pydantic v2 DTO（与 ORM 隔离）
│   │   ├── auth.py
│   │   ├── conversation.py
│   │   ├── message.py
│   │   ├── knowledge.py
│   │   └── task.py
│   └── routers/
│       ├── health.py             #   /healthz /readyz
│       ├── auth.py               #   /api/v1/auth/*（登录/刷新/me）
│       ├── conversations.py      #   /api/v1/conversations
│       ├── messages.py           #   含 SSE: .../messages:stream
│       ├── knowledge.py          #   CRUD + 触发 ingest
│       ├── retrieval.py          #   POST /api/v1/retrieval/search
│       ├── tasks.py              #   查询 ARQ 任务
│       └── ws_chat.py            #   WS /ws/chat/{conversation_id}
│
├── core/                         # ★ 领域核心（不 import api/ui/db 的 session）
│   ├── llm/                      #   Ollama 封装（从 utils/model 搬）
│   │   ├── ollama_client.py
│   │   └── base.py
│   ├── memory/                   #   Conversation / Message 领域模型
│   │   ├── models.py
│   │   └── service.py
│   ├── knowledge/
│   │   ├── models.py
│   │   ├── loader.py             #   读取 knowledge/ 目录
│   │   ├── chunker.py            #   markdown → chunks
│   │   └── training.py           #   TrainingDataGenerator
│   ├── retrieval/
│   │   ├── base.py               #   Retriever 抽象
│   │   ├── pgvector_retriever.py #   生产实现
│   │   └── keyword.py            #   降级/离线实现
│   ├── embedding/
│   │   └── ollama_embedder.py    #   调用 ollama /api/embeddings
│   └── chat_service.py           #   ★ 编排: 检索 → 拼 prompt → LLM → 落库 → 推 Redis
│
├── db/                           # ★ 持久化
│   ├── session.py                #   async engine + AsyncSessionLocal
│   ├── base.py                   #   DeclarativeBase
│   ├── models/                   #   SQLAlchemy ORM
│   │   ├── user.py
│   │   ├── conversation.py
│   │   ├── message.py
│   │   ├── article.py
│   │   ├── embedding.py          #   pgvector 列
│   │   └── task.py
│   └── repositories/             #   仓储，隔离 ORM
│
├── cache/                        # ★ Redis 封装
│   ├── client.py
│   ├── keys.py                   #   key 命名空间常量
│   ├── rate_limit.py
│   └── pubsub.py                 #   WS 广播 token stream
│
├── workers/                      # ★ ARQ 后台任务
│   ├── worker.py                 #   WorkerSettings
│   ├── tasks_train.py            #   LoRA 训练
│   └── tasks_ingest.py           #   知识入库 + embedding
│
├── ui/                           # ★ CLI 视觉层（opencode 风格，见 §11）
│   ├── theme.py
│   ├── console.py
│   ├── chat_view.py
│   ├── prompt.py
│   └── markdown.py
│
├── utils/                        # 仅保留真·通用工具
│   ├── logger.py
│   ├── config.py                 #   过渡期保留；新代码用 app/settings.py
│   ├── data_loader.py
│   └── task_scheduler.py
│
├── settings.py                   # ★ pydantic-settings 统一配置入口
│
├── migrations/                   # ★ Alembic
├── scripts/                      # 离线脚本（训练、数据生成）
├── configs/                      # JSON 训练配置
├── knowledge/ conversations/ data/  # 运行时数据目录
├── docker/
│   ├── Dockerfile.app            # ★
│   └── Dockerfile.trainer        # ★
├── docker-compose.yml            # ★ 扩展
├── .env.example                  # ★
├── alembic.ini                   # ★
├── Makefile                      # ★ 根 Makefile，统一入口，见 §8.4
│
├── web-app/                      # ★ 身份平台 / 业务前端 (Vue3 + Vite + TS)
│   ├── src/
│   │   ├── api/                  #   Axios 实例 + 各领域 API
│   │   ├── components/           #   ★ 每个组件一个目录，入口 index.vue + index.ts（见 §11b.9）
│   │   │   ├── TokenCard/
│   │   │   │   ├── index.vue
│   │   │   │   ├── index.ts
│   │   │   │   └── index.module.less
│   │   │   ├── ApiStatusBadge/
│   │   │   └── base/             #   ★ Element Plus 二次封装（唯一出口）
│   │   │       ├── BaseButton/
│   │   │       ├── BaseInput/
│   │   │       ├── BaseEmailField/
│   │   │       ├── BasePasswordField/
│   │   │       ├── BaseCard/
│   │   │       └── BaseEmpty/
│   │   ├── composables/
│   │   ├── i18n/                 #   zh-CN / en-US
│   │   ├── layouts/              #   AuthLayout/ AppLayout/  （目录化）
│   │   ├── mocks/                #   msw handlers（前端独立演示）
│   │   ├── router/               #   guards 登录守卫
│   │   ├── stores/               #   auth / ui
│   │   ├── styles/               #   tokens.less / reset.less / element-override.less
│   │   ├── types/                #   与 §5 DTO 对齐
│   │   └── views/                #   LoginView/ DashboardView/ TokenView/ ProfileView/  （目录化）
│   ├── public/
│   ├── uno.config.ts
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── eslint.config.js
│   ├── .env.example
│   └── package.json
│
├── pyproject.toml
├── main.py                       # 薄壳: python main.py → app.cli:main
├── README.md                     # 用户向
└── AGENTS.md                     # 本文件
```

---

## 3. Architecture Boundaries（Agent 红线）

严格的**导入方向**（违反即 reject）：

```
         ui  ───▶ app
                   │
        api ──▶ app ──▶ core ──▶ db / cache / workers.task_defs
                                        ▲
                                        │
                        workers(run-time) ──▶ core
```

具体规则：

1. `core/` **不得** `import` `api/`、`ui/`、`app/`、`fastapi`、`uvicorn`。
2. `ui/` **不得** `import` `core/`、`db/`、`cache/`、`api/`。它只被 `app/chat_app.py` 使用。
3. `api/routers/*` **只做 DTO 转换 + 调用 core service**，不写 SQL、不直接用 SQLAlchemy Session（通过仓储或 service）。
4. `db/models/` **不得** `import` `schemas/`（反过来 OK）。
5. `utils/` **不得** `import` 除 `utils/` 自身以外的项目模块；它是纯通用工具。
6. 任何新增跨层依赖，**先改 AGENTS.md 再改代码**。

### 3.1 Dependency Diagram (v0.5 +)

```mermaid
flowchart LR
    main[main.py shim] --> cli[app.cli]
    cli --> chat[app.chat_app]
    chat --> ui[ui]
    chat -.future.-> core[core]
    ui -.no.-> core
    ui -.no.-> db
    ui -.no.-> api
    api --> chat
    api --> core
    core --> db
    core --> cache
    workers --> core
```

规则映射：
- 实线 = 允许；`-.no.-` = 红线禁止。
- `ui/` 只被 `app/chat_app` 消费，且从不反向依赖 `core/` `db/` `api/`。
- `app/` 是唯一同时知道 `ui/` 与 `core/` 的层。

---

## 4. Data Model（契约）

所有字段变更须走 Alembic migration，并同步本节。

```sql
-- users
id              bigserial pk
email           citext unique not null
password_hash   text not null
display_name    text
is_active       boolean default true
created_at      timestamptz default now()

-- conversations
id              uuid pk default gen_random_uuid()
user_id         bigint fk users(id) on delete cascade
title           text
metadata        jsonb default '{}'
created_at      timestamptz default now()
updated_at      timestamptz default now()
ended_at        timestamptz null
-- idx: (user_id, updated_at desc)

-- messages
id              uuid pk default gen_random_uuid()
conversation_id uuid fk conversations(id) on delete cascade
role            text check (role in ('user','assistant','system'))
content         text not null
tokens          int
latency_ms      int
metadata        jsonb default '{}'
created_at      timestamptz default now()
-- idx: (conversation_id, created_at)

-- articles  (来自 knowledge/ 目录的元数据入库)
id              bigserial pk
slug            text unique not null          -- 对应文件名
title           text not null
category        text
tags            text[] default '{}'
content_md      text not null
author          text
difficulty      text
reading_time    text
source_path     text                          -- 原文件路径
created_at      timestamptz default now()
updated_at      timestamptz default now()
-- idx: gin(tags), btree(category)

-- article_embeddings
id              bigserial pk
article_id      bigint fk articles(id) on delete cascade
chunk_index     int not null
chunk_text      text not null
embedding       vector(768)                   -- nomic-embed-text dim
-- idx: ivfflat (embedding vector_cosine_ops) with (lists=100)

-- tasks (ARQ 任务的业务视图，不是 ARQ 内部队列)
id              uuid pk default gen_random_uuid()
user_id         bigint fk users(id)
type            text check (type in ('ingest','train'))
status          text check (status in ('queued','running','succeeded','failed'))
payload         jsonb
result          jsonb
error           text
created_at      timestamptz default now()
started_at      timestamptz
finished_at     timestamptz
```

**扩展注意**：`gen_random_uuid()` 需要 `pgcrypto`；`vector` 列需要 `vector` 扩展；两者都通过 `pgvector/pgvector:pg16` 镜像 + `CREATE EXTENSION IF NOT EXISTS ...` 的 migration 启用。

---

## 5. API Contract

### 5.1 REST（版本前缀 `/api/v1`）

| Method | Path | Auth | 说明 |
|---|---|---|---|
| GET | `/healthz` | 公开 | liveness，只返回 `{"ok":true}` |
| GET | `/readyz` | 公开 | 检查 db/redis/ollama 连通 |
| POST | `/api/v1/auth/login` | 公开 | body: `{email, password}` → `{access_token, refresh_token, expires_in}` |
| POST | `/api/v1/auth/refresh` | refresh token | 新 `access_token` |
| GET | `/api/v1/auth/me` | Bearer | 当前用户 |
| POST | `/api/v1/conversations` | Bearer | 新建会话 |
| GET | `/api/v1/conversations?limit=&cursor=` | Bearer | 游标分页 |
| GET | `/api/v1/conversations/{id}` | Bearer | 详情 + 最近 N 条消息 |
| DELETE | `/api/v1/conversations/{id}` | Bearer | 软删 |
| GET | `/api/v1/conversations/{id}/messages?limit=&before=` | Bearer | 历史消息 |
| POST | `/api/v1/conversations/{id}/messages` | Bearer | 非流式发送，返回完整 assistant 消息 |
| POST | `/api/v1/conversations/{id}/messages:stream` | Bearer | **SSE 流式**，事件见 §5.3 |
| POST | `/api/v1/knowledge` | Bearer | 新增文章 |
| GET | `/api/v1/knowledge` | Bearer | 列表 |
| POST | `/api/v1/knowledge/{id}/ingest` | Bearer | 触发 embedding（异步），返回 `task_id` |
| POST | `/api/v1/retrieval/search` | Bearer | body: `{query, top_k?}` → `{hits:[{article_id, chunk_text, score}]}` |
| POST | `/api/v1/tasks/train` | Bearer (admin) | 提交 LoRA 任务 |
| GET | `/api/v1/tasks/{id}` | Bearer | 任务状态 |

**鉴权头**：`Authorization: Bearer <jwt>`。所有非公开端点无 token 返回 `401 { "code":"unauthorized" }`。权限不足返回 `403`。

**错误模型**（所有 4xx/5xx 统一）：
```json
{ "code": "string_error_code", "message": "human readable", "request_id": "uuid", "details": {} }
```

### 5.2 WebSocket

- `WS /ws/chat/{conversation_id}?token=<jwt>`（浏览器 WS 不能自定义 header，允许 query 传 token；CLI 可用 `Sec-WebSocket-Protocol: bearer, <jwt>`，server 两种都接受）。
- 建立后 server 立即发 `{"type":"ready"}`。
- 心跳：server 每 30s 发 `{"type":"ping"}`，client 回 `{"type":"pong"}`；60s 无 pong 断开。

### 5.3 统一流式事件协议（SSE 与 WS 一致）

不管走 SSE 还是 WS，**事件名和 payload 结构一致**。SSE 形式是 `event: <type>\ndata: <json>\n\n`；WS 形式是 `{"type":..., ...}`。

| type | 方向 | payload |
|---|---|---|
| `user_message` | C→S (仅 WS) | `{content: str}` |
| `retrieval` | S→C | `{hits: [{article_id, chunk_text, score}]}`（可选，RAG 开启时） |
| `token` | S→C | `{delta: str}` 多次下发 |
| `done` | S→C | `{message_id: uuid, usage:{prompt_tokens,completion_tokens}, duration_ms}` |
| `error` | S→C | `{code: str, message: str}` |
| `ping`/`pong` | 双向 | `{}` |

---

## 6. Authentication Model

### 6.1 身份来源
- **唯一身份源是 Web 登录平台**（未来 Vue3 前端 + 本 FastAPI 的 `/api/v1/auth/login`）。
- 登录凭证：邮箱 + 密码（bcrypt 存哈希）。
- 登录成功签发 **access_token (15 min)** 与 **refresh_token (7 day)**，HS256，`secret` 来自 `JWT_SECRET` 环境变量。
- JWT claims：
  ```json
  { "sub": "<user_id>", "email": "...", "scope": ["user"], "iat": ..., "exp": ..., "jti": "..." }
  ```

### 6.2 CLI 如何拿 token
1. `rag-chat auth login --email you@x.com` → 交互式输密码 → 调 `/api/v1/auth/login`
2. token 写入 `~/.config/rag-chat/token.json`（`chmod 600`），字段：`{access_token, refresh_token, expires_at}`。
3. 后续所有 CLI 子命令自动带 `Authorization: Bearer`；access 过期自动用 refresh 续；refresh 也失效则提示重新登录。
4. `rag-chat auth logout` 清文件。

### 6.3 受保护范围
- **公开**：`/healthz`、`/readyz`、`/api/v1/auth/login`、`/api/v1/auth/refresh`、OpenAPI docs（生产关掉）。
- **受保护**：其余所有 `/api/v1/*` 和 `/ws/chat/*`。
- **管理员**（claim `scope` 含 `admin`）：`/api/v1/tasks/train`、未来的用户管理。

### 6.4 安全红线
- 任何新增受保护端点，**默认走 `Depends(get_current_user)`**；要开放须显式加到 `PUBLIC_PATHS` 白名单且在 PR 说明。
- 不准把 token 写日志；`access log` 要 mask `Authorization` 头。
- 密码强度：≥ 8 位，包含数字+字母（`pydantic` validator）。
- 禁止在 URL query 里长期带 token（WS 建连除外，因浏览器限制）。

---

## 7. Environment & Configuration

单一配置入口 `settings.py`（`pydantic-settings`）。所有环境变量在此声明，其它模块**禁止直接读 `os.environ`**。

`.env.example`（示例）：
```
# app
APP_ENV=dev                    # dev | prod
LOG_LEVEL=INFO
REQUEST_ID_HEADER=X-Request-ID

# auth
JWT_SECRET=change-me-in-prod
JWT_ALG=HS256
ACCESS_TOKEN_TTL_MIN=15
REFRESH_TOKEN_TTL_DAY=7

# db
DATABASE_URL=postgresql+asyncpg://rag:rag@postgres:5432/ragdb

# redis
REDIS_URL=redis://redis:6379/0

# ollama
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_CHAT_MODEL=qwen2.5:1.5b
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_TIMEOUT=120

# retrieval
RAG_ENABLED=true
RAG_TOP_K=4
RAG_MIN_SCORE=0.25

# rate limit
RATE_LIMIT_PER_MIN=60
```

**过渡兼容**：现存 `config.json` 仍然可读，`settings.py` 提供 `load_legacy_config()` 合并。新代码禁止再读 `config.json`。

---

## 8. Running the Project

### 8.1 本地直跑（无 docker）
```bash
uv sync
# 需要本机有 ollama，已 pull qwen2.5:1.5b、nomic-embed-text
# 需要本机 postgres(pgvector) + redis
alembic upgrade head
uv run uvicorn app.server:app --reload      # Web
uv run python main.py chat                   # CLI
```

### 8.2 Docker Compose（推荐）
```bash
cp .env.example .env
docker compose --profile web up -d           # postgres + redis + ollama + api + worker
docker compose --profile cli run --rm cli    # 交互式 CLI
docker compose --profile train run --rm trainer   # 一次性训练
```

Profiles：
- `web`：api + worker + postgres + redis + ollama
- `cli`：ollama + cli（共享 api 也可）
- `train`：trainer（胖镜像，含 torch）

### 8.3 一次性命令
```bash
docker compose exec api alembic upgrade head
docker compose exec api python -m app.cli ingest ./knowledge       # 全量知识入库
docker compose exec api python -m app.cli user create --email ...  # 建用户（管理员）
```

### 8.4 Makefile Reference

根目录 `Makefile` 是所有日常命令的**唯一入口**。Agent 新增脚本应先考虑添加 target，而不是在文档里堆 shell。

**快速参考**（完整列表 `make help`）：

| Group | Target | 作用 |
|---|---|---|
| Setup | `make install` | `install.py` + `install.web` + `install.hooks` |
| Setup | `make env` | 基于 `.env.example` 创建 `.env` |
| Dev | `make dev.api` / `dev.worker` / `dev.cli` / `dev.web` | 本地直跑各进程 |
| Dev | `make dev` | tmux 同时拉起 api + worker + web |
| Docker | `make up` / `down` / `logs SERVICE=api` / `rebuild` | 容器编排 |
| Docker | `make up.cli` / `up.train` | profile 一次性容器 |
| DB | `make db.up` / `db.migrate` / `db.rev m="..."` / `db.shell` | 数据库生命周期 |
| DB | `make db.reset` | **DEV 专用**，drop + recreate + migrate（二次确认） |
| Ollama | `make ollama.pull` / `ollama.ps` | 拉/列模型 |
| Quality | `make lint` / `fmt` / `test` / `check` | 质量门 |
| Seed | `make seed.user` / `ingest` | 初始化 |
| Build | `make build.api` / `build.trainer` / `build.web` | 构建镜像/产物 |
| Clean | `make clean` / `nuke` | `nuke` 会删卷，危险 |

**约定**：
- 所有 Python 命令走 `uv run`；所有前端命令走 `pnpm --dir web-app`。
- 可覆盖变量：`make logs SERVICE=api`、`make up PROFILE=cli`。
- 新增 target 须带 `## 注释`，`make help` 会自动展示。

---

## 9. Streaming Design Decision

**为什么同时要 SSE 和 WS？**（给 Agent 看清楚，后续别乱改）

| 场景 | 选 | 理由 |
|---|---|---|
| 浏览器里"一次发一条消息、等回答" | **SSE** | 单向、走普通 HTTP、易过反代、易重试；浏览器 `EventSource` 足够 |
| 长驻对话界面、多端同步、服务端推送非用户消息（如工具调用提示） | **WebSocket** | 双向、低延迟 |
| CLI 交互式聊天 | **WS**（也支持 SSE 作为降级） | CLI 有状态更合适 |

两者事件 schema **必须一致**（见 §5.3）。后端实现上，`core.chat_service.stream_reply(...)` 产出 `AsyncIterator[Event]`，`api/routers/messages.py` 把它适配成 SSE，`api/routers/ws_chat.py` 适配成 WS 帧。**禁止**写两套业务逻辑。

---

## 10. Background Tasks (ARQ)

- Worker 入口：`workers/worker.py::WorkerSettings`
- 任务命名规范：`tasks_<domain>.py`，函数以 `task_` 前缀。
- 任务幂等：`payload` 里必须有 `idempotency_key`；`tasks` 表上 `unique(type, idempotency_key)` where status in (queued, running, succeeded)。
- 长任务须周期性 `ctx['redis'].set(f"task:{task_id}:heartbeat", ts, ex=30)`。
- 训练任务在 `trainer` profile 独立镜像跑（避免 api 镜像被 torch 拖胖）。

---

## 11. CLI UI Conventions (opencode-style)

- **零 emoji** 原则；仅在错误处可用 `✗`、成功 `✓`、提示 `›`、分隔 `│` `─`。
- 消息采用 `│ ` 前缀 + 角色色标：user=green，assistant=bright_cyan，system=grey50。
- Banner 单行：`rag-chat · qwen2.5:1.5b · ready`。
- 输入走 `prompt_toolkit`：多行（Esc+Enter 发送）、历史（↑↓）、底部 toolbar 显示快捷键。
- 斜杠命令统一分发器（`/quit /clear /new /model /retrieve on|off /login /logout`）。
- 流式渲染使用 `rich.live.Live` + 增量 Markdown。

UI 模块对外只暴露 `ChatView`、`PromptSession`、`Theme` 三个符号。禁止在 `ui/` 内部调用 `core/`、`db/`、`cache/`。

---

## 11b. Web UI Conventions (`web-app/`)

面向未来 Vue3 业务页，当前聚焦"身份平台"：邮箱登录 → 拿到 JWT → 展示并让用户复制给 CLI 使用。

### 11b.1 视觉与交互
- **暗色优先**（tokens 默认 `data-theme="dark"`），支持切换 `light`；切换状态持久化 `localStorage.rag_chat_theme`。
- 主色青绿 `#22d3ee`，与 CLI opencode 风呼应。
- 无花哨动画：过渡 ≤ 200ms；禁用弹窗广告式组件。
- 等宽字体展示 token / code，使用 `JetBrains Mono` → `IBM Plex Mono` 回退链。

### 11b.2 样式三层分工（强约束）

| 层 | 用途 | 写在哪 |
|---|---|---|
| **UnoCSS 原子类** | 布局、间距、响应式、一次性微调 | 直接写在 `<template>` 的 `class` 属性上 |
| **Less + CSS Modules** | 组件自身结构化样式、状态、Element 深度样式 | 每个 `.vue` 同名 `.module.less` |
| **全局 `styles/*.less`** | design tokens、reset、Element 主题覆盖 | `src/styles/` |

**禁止**：
- ❌ 在业务 `.vue` 里写 `<style>` 全局样式（`<style module>` 或独立 `.module.less` 二选一）。
- ❌ 跨层选择器（`.a .b .c`）、嵌套超过 3 层。
- ❌ 在模板里硬编码颜色（必须用 token 或 UnoCSS 语义类 `text-brand`）。

### 11b.3 "结构化书写"（BEM-ish + 结构对齐）

- class 命名：`block__element--modifier`（CSS Modules 下访问 `styles.block__element`）。
- `.module.less` 里嵌套顺序必须等于 `<template>` 子元素出现顺序。
- 每个组件顶层用 `styles.<componentCamelCase>` 作为根类。

### 11b.4 Element Plus 二次封装规范

- 位置：`src/components/base/`，文件以 `Base` 前缀。
- **页面和业务组件禁止 `import { ElXxx } from 'element-plus'`**。ESLint `no-restricted-imports` 强制（仅 `src/components/base/**` 豁免）。
- 每个 `BaseXxx.vue` 必须：
  1. 只暴露**业务语义 props**（例：`BaseEmailField` 不暴露 `type`）。
  2. 附带同名 `.module.less` 做结构与 `:global(.el-xxx)` 深度覆盖。
  3. 完整 TS 类型，`defineEmits`/`defineProps`/`defineExpose` 齐全。
- 自动注册：`unplugin-vue-components` 仅扫描 `src/components/base/`，按需引入 Element Plus 的 CSS。

### 11b.5 Auth 流程（Web ↔ CLI）
1. 用户在 `/login` 输入邮箱密码 → `POST /api/v1/auth/login`。
2. token 写 `localStorage`：`rag_chat_access` / `rag_chat_refresh` / `rag_chat_expires_at`。
3. `/dashboard` 与 `/token` 通过 `TokenCard` 展示 token，一键复制 `rag-chat auth set-token "<token>"`。
4. CLI 读取 token 后按 §6.2 存 `~/.config/rag-chat/token.json`。
5. Axios 401 拦截器自动调用 `/auth/refresh`；失败跳回 `/login?redirect=...`。

### 11b.6 i18n
- `vue-i18n` + `src/i18n/locales/{zh-CN,en-US}.json`。默认跟随 `VITE_DEFAULT_LOCALE`，fallback `zh-CN`。
- 所有面向用户的文本**必须**走 `t(...)`；硬编码中英文字面量在 lint 阶段不允许（新加 rule 后续落地）。

### 11b.7 数据流纪律
- 所有 HTTP 调用**必须**走 `src/api/*.ts`（内部用 `http.ts`）。业务组件禁止直接 `fetch` 或 `axios.create`。
- 与后端的契约**只在 `src/types/api.ts` 定义一次**，对应 AGENTS.md §5。

### 11b.8 目录职责再强调
`views/` 只做页面编排 → `components/`（业务） → `components/base/`（UI 原语） → `api/` → `stores/`。禁止反向依赖。

### 11b.9 组件目录化（★ 硬约束）

**每个 Vue 组件/视图/布局一个目录**，入口固定 `index.vue` + `index.ts`。**禁止**在 `views/`、`layouts/`、`components/`、`components/base/` 下出现平铺的 `.vue` / `.module.less`（除 `App.vue` 外）。

```
<ComponentDir>/
├── index.vue              # 主入口（必须）
├── index.ts               # TS 入口 re-export（必须，让 `@/foo` 路径可解析）
├── index.module.less      # 根样式（按需）
├── types.ts               # 本组件私有类型（按需）
├── composables.ts         # 本组件私有 hook（按需）
└── components/            # 仅被本组件消费的子组件（按需）
    └── SubThing/
        ├── index.vue
        ├── index.ts
        └── index.module.less
```

**Import 写法（统一）**：
```ts
// ✅ 目录 + index，路径短且稳定
import LoginView from '@/views/LoginView'
import BaseButton from '@/components/base/BaseButton'

// ❌ 带 .vue 后缀
import LoginView from '@/views/LoginView/index.vue'
// ❌ 平铺文件（本仓库已废弃）
import LoginView from '@/views/LoginView.vue'
```

**为什么需要 `index.ts`**：TS 不会像 Node 自动解析 `dir → dir/index.vue`；加一行 `export { default } from './index.vue'` 让 TS/ESLint/IDE/Vite 一致解析。新增组件必须同时建 `index.vue` + `index.ts`。

**样式文件命名**：组件根类用 `styles.<dirCamelCase>`（如 `LoginView` → `styles.loginView`），BEM-ish 嵌套遵循 §11b.3。

**自动注册**：`unplugin-vue-components` 扫描 `src/components/base/**`，目录里找到 `index.vue` 会把组件名注册为**目录名**（`BaseButton` → `<BaseButton />`），行为与平铺时一致。

---

## 12. Coding Conventions

- **Python ≥ 3.10**，优先使用 `X | None`、`list[str]` 新语法。
- 全异步路径（api / core / db / cache）用 `async def`；同步工具留在 `utils/` 和 `scripts/`。
- **类型注解强制**（`api/`、`core/`、`db/`、`cache/`、`workers/`、`settings.py`）；`mypy --strict` 在 CI。
- 错误处理：
  - 领域层抛**领域异常**（如 `ConversationNotFound`），定义在 `core/errors.py`。
  - `api/errors.py` 将其映射到 HTTP code，不泄露堆栈。
- 日志：用 `utils.logger.get_logger(__name__)`；禁止 `print()` 出现在 `api/core/db/cache/workers`（`ui/` 除外）。
- 命名：模块/函数 `snake_case`，类 `PascalCase`，常量 `UPPER_SNAKE`。
- 注释语言：**中文可用**，但公开 API 的 docstring 用英文（FastAPI 会展示到 OpenAPI）。
- 不要再用现成代码里的 `from utils import *` 式的 re-export（`utils/__init__.py` 要瘦身到只留真通用工具）。

---

## 13. Testing & Quality Gates

- `pytest` 布局：
  ```
  tests/
    unit/          # core/ 纯逻辑
    integration/   # db + redis + ollama(可 mock)
    api/           # httpx.AsyncClient 打 FastAPI
  ```
- 所有 PR 必须过：`ruff check`、`ruff format --check`、`mypy`、`pytest -q`。
- 新增 API 必须同时新增至少一个 happy path + 一个 401/403 用例。
- 覆盖率门槛：`core/` ≥ 80%，`api/` ≥ 70%。
- Ollama/LLM 在测试中 **默认 mock**（`conftest.py` 提供 `fake_ollama` fixture）。

---

## 14. Migrations (Alembic)

- `alembic revision --autogenerate -m "<desc>"` → 人工检查 → `alembic upgrade head`。
- **禁止**直接 `CREATE TABLE` 在代码里运行。`db/models/` 改动必须伴随 migration。
- 初始 migration 里 `CREATE EXTENSION IF NOT EXISTS pgcrypto; CREATE EXTENSION IF NOT EXISTS vector;`。
- 生产环境 migration 前先在 staging 跑 + `pg_dump` 备份。

---

## 15. Migration Plan (现状 → 目标)

当前仓库大量逻辑仍在 `utils/` 和 `main.py`。AI agent 在过渡期须遵守：

| 阶段 | 新增/保留 | 删除/废弃 |
|---|---|---|
| P1 UI 独立 | 新建 `ui/`，`main.py` 切入 `app/cli.py` + `app/chat_app.py`；style 切 opencode | `utils/console_ui.py` 先保留为 deprecated shim，三次 PR 后删除 |
| P2 目录分层 | 新建 `core/`，把 `utils/model/*` → `core/llm/`，`utils/chat_memory.py` 拆到 `core/memory/`，`utils/knowledge_base.py` 拆到 `core/knowledge/` | 老路径保留 import shim；`scripts/` 内改到新路径 |
| P3 Docker | 新增 `docker/Dockerfile.app`、`Dockerfile.trainer`、`.dockerignore`；`docker-compose.yml` 加 postgres/redis/api/worker/trainer 与 profiles；`version: '3.8'` 删除 | — |
| P4 DB & Auth | 新增 `db/`、`migrations/`、`settings.py`、`api/auth`；`conversations/` 目录下的旧 JSON 通过一次性脚本迁入 PG | `ConversationManager.save_conversation()` 到 JSON 的逻辑保留为"本地离线模式"fallback |
| P5 API & WS | 新增 `api/` 所有 routers；`app/server.py` 可启动 | — |
| P6 RAG | 新增 `core/retrieval/`、`core/embedding/`、`workers/tasks_ingest.py`；`chat_service` 接入 | 训练数据生成脚本保留 |
| P7 Web Identity Portal | 新增 `web-app/`（Vue3 + Vite + TS + UnoCSS + Less(CSS Modules) + Element Plus 二次封装）；登录/Token/Profile 页面；默认走 msw mock，可切真实后端 | — |

**兼容承诺**：在 P1~P5 任一阶段，`python main.py`（或等价命令）必须仍能启动一个可用的 CLI 聊天。P7 独立于后端阶段，随时可并行推进（用 msw mock）。

---

## 16. Do / Don't for AI Agents

**DO**
- 新代码一律写在 §2 的目标路径。
- 新表/新列必须同步：`db/models/` + alembic + AGENTS.md §4。
- 新接口必须同步：`api/routers/` + `api/schemas/` + AGENTS.md §5 + 测试。
- 改配置必须同步：`settings.py` + `.env.example` + AGENTS.md §7。
- 任何 LLM 调用必须可 mock；注入 `OllamaClient` 而不是在函数内 new。
- 任何会阻塞事件循环 > 50ms 的调用放进 `workers/`。

**DON'T**
- ❌ 在 `api/` 里写 SQL。
- ❌ 在 `core/` 里 `from fastapi import ...` 或 `from rich import ...`。
- ❌ 直接 `os.getenv("...")`（除 `settings.py` 外）。
- ❌ 把密码、token、email 写进日志或错误 message。
- ❌ 新增三方服务（另一个向量库 / 另一个 MQ / 另一个搜索引擎）前不更新 §1 技术栈决策表。
- ❌ 绕过 Alembic 直接改表结构。
- ❌ 在容器镜像里装 `torch` 给 `api` 用（胖）。训练相关依赖只放 `trainer` 镜像。
- ❌ 擅自创建 `.md` 文档文件。如果需要，先在 AGENTS.md 或 `docs/` 已有文件里改。

**Web-specific DON'T（`web-app/`）**
- ❌ 业务代码直接 `import { ElXxx } from 'element-plus'`（必须通过 `components/base/`）。
- ❌ 业务组件直接 `fetch` / 裸 `axios`（必须走 `src/api/*`）。
- ❌ 把 JWT 放进 URL 参数长期使用（WebSocket 握手除外）。
- ❌ 页面里硬编码中英文字符串（必须 `t()`）。
- ❌ 页面里硬编码颜色值（必须用 token 或 UnoCSS 语义类）。
- ❌ 绕过 `stores/auth` 自行读写 `localStorage` token 键。
- ❌ 在 `<template>` 里堆超过 ~10 个原子类做复杂样式（超过就搬进 `.module.less`）。

---

## 17. Common Workflows (SOP)

### 17.1 新增一个 REST 接口
1. `api/schemas/<domain>.py` 加 request/response Pydantic。
2. `core/<domain>/service.py` 加业务方法（纯 async，不依赖 FastAPI）。
3. `api/routers/<domain>.py` 加 route，`Depends(get_current_user)`。
4. 测试：`tests/api/test_<domain>.py` 至少 200 + 401。
5. 更新 AGENTS.md §5 表格。

### 17.2 新增一张表
1. `db/models/<name>.py`：ORM 类。
2. `alembic revision --autogenerate -m "add <name>"`，人工检查 SQL。
3. `db/repositories/<name>_repo.py`：封装查询。
4. `core/` 暴露业务方法。
5. 更新 AGENTS.md §4。

### 17.3 新增一个后台任务
1. `workers/tasks_<domain>.py`：`async def task_xxx(ctx, payload): ...`
2. 注册到 `workers/worker.py::WorkerSettings.functions`。
3. API 层通过 `await ctx_pool.enqueue_job("task_xxx", payload, _job_id=idempotency_key)` 入队。
4. 在 `tasks` 业务表记录。
5. 测试：mock redis 验证入队；集成测试跑 worker 一次。

### 17.4 接入知识（文章 → 向量）
1. 文章走 `POST /api/v1/knowledge` 入 `articles` 表。
2. 触发 `POST /api/v1/knowledge/{id}/ingest` → ARQ 任务：
   - `chunker.split(content_md, 800 tokens, overlap 100)`
   - 对每个 chunk 调 `OllamaEmbedder.embed()`（`/api/embeddings`，model=`nomic-embed-text`）
   - 批量 `INSERT INTO article_embeddings`
3. 检索：`PgVectorRetriever.search(query_embedding, top_k)` SQL：
   ```sql
   SELECT article_id, chunk_text,
          1 - (embedding <=> :qvec) AS score
   FROM article_embeddings
   ORDER BY embedding <=> :qvec
   LIMIT :k;
   ```

### 17.5 启用 RAG 到对话
`core/chat_service.stream_reply` 伪代码：
```python
async def stream_reply(conv_id, user_text) -> AsyncIterator[Event]:
    if settings.RAG_ENABLED:
        q_vec = await embedder.embed(user_text)
        hits = await retriever.search(q_vec, top_k=settings.RAG_TOP_K)
        hits = [h for h in hits if h.score >= settings.RAG_MIN_SCORE]
        if hits:
            yield Event("retrieval", hits=hits)
        context = build_context(hits)
    else:
        context = ""

    messages = build_messages(system_prompt(context), history, user_text)
    async for chunk in ollama.stream_chat(messages):
        yield Event("token", delta=chunk)

    saved = await messages_repo.save_assistant(...)
    yield Event("done", message_id=saved.id, usage=..., duration_ms=...)
```

---

## 18. Glossary

| Term | 含义 |
|---|---|
| **RAG** | Retrieval-Augmented Generation，检索增强生成 |
| **Chunk** | 文章切分后的文本片段，嵌入的最小单元 |
| **ARQ** | Async Redis Queue，异步任务队列库 |
| **pgvector** | Postgres 向量扩展 |
| **SSE** | Server-Sent Events，HTTP 单向流式 |
| **JWT** | JSON Web Token |
| **LoRA** | Low-Rank Adaptation，大模型低秩微调 |
| **Event Schema** | §5.3 定义的统一流式事件协议 |

---

## 19. Change Log of This Document

- v0.1 — 初版：定义 FastAPI + Redis + Postgres(pgvector) + Ollama + JWT 目标架构，给出迁移路径与 Agent 红线。
- v0.2 — 增补：
  - §1 Tech Stack 加 Web 小节（Vue3 + UnoCSS + Less(CSS Modules) + Element Plus 二次封装 + msw）。
  - §2 目录加 `web-app/` 与 `Makefile`。
  - §8.4 Makefile Reference（根目录 `Makefile` 落地）。
  - §11b Web UI Conventions（视觉、样式三层分工、BEM-ish 结构化书写、Element Plus 二次封装、Auth 流程、数据流纪律）。
  - §15 迁移路径加 P7 Web Identity Portal。
  - §16 Don'ts 加前端红线。
- v0.3 — 组件目录化：
  - §11b.9 新增硬约束：每个 Vue 组件/视图/布局一个目录，入口 `index.vue` + `index.ts`。
  - §2 `web-app/` 目录图更新为目录化风格。
  - 现存 `views/`、`layouts/`、`components/` 全部迁移完成，旧平铺文件已删除。
- v0.4 — P0 Bootstrap settings.py (pydantic-settings) + .env.example：
  - 根级 `settings.py`（7 个分组 BaseModel + 顶层 `Settings`）作为唯一配置入口。
  - `.env.example` 完全对齐 §7；支持扁平名（`JWT_SECRET`）与嵌套名（`AUTH__JWT_SECRET`）等价。
  - `env=dev` 无 secret 自动 fallback `dev-insecure-secret` + 警告；`env=prod` 必须显式配置。
  - 仓库"干净化"：删除 `config.json`、`utils/`、`main.py`、`docs/*.md`、`configs/*.json`、`data/train.json`、历史 `conversations/` 等历史包袱，仅保留 AGENTS.md / openspec / Makefile / docker-compose / pyproject 等元数据骨架。
  - 训练依赖（`torch`/`transformers`/`peft`/`bitsandbytes`/`datasets`）移到 `[project.optional-dependencies].train`。
  - 正式登记 capability spec：`openspec/specs/settings/spec.md`。
  - Change 已归档：`openspec/changes/archive/2026-04-24-bootstrap-settings-and-env/`。
- v0.5 — P1 Restructure CLI UI (opencode-style)：
  - 新建 `ui/`（`theme` / `console` / `markdown` / `chat_view` / `prompt`），对外只暴露 `ChatView / PromptSession / Theme` 三个符号，严格遵循 §3 边界。
  - 新建 `app/`（`cli` / `chat_app`），`main.py` 瘦身为三行 shim。
  - `ChatView.stream_assistant` 接入 §5.3 `Event` TypedDict，为未来 SSE/WS 复用同一视图层。
  - 输入走 `prompt_toolkit`：多行（`Esc+Enter`）、`F2` 备选、`Ctrl-L` 清屏、`↑↓` 历史、底部 toolbar。
  - 斜杠命令统一分发器（`/quit /exit /clear /new /help`；`/model /retrieve /login /logout` 预留占位）。
  - 偏离 tasks.md §7.2：`LegacyOllamaReplyProvider` 改为内置 `EchoReplyProvider`（v0.4 干净化已删除 `utils/model/*`，"遗留适配"无对象可适配）；真实 LLM 由后续 `split-core-domain-layer` 接入。
  - 偏离 tasks.md §9.1 / §10.1–10.3：v0.4 干净化已删除 `main.py` 旧版与 `utils/console_ui.py`，不再需要备份与 deprecated shim。
  - 新依赖：`prompt_toolkit>=3.0.43`。
  - 测试：`tests/unit/ui/test_theme.py` / `test_chat_view.py` / `test_prompt.py` + `tests/integration/test_cli_boot.py`；`uv run pytest -q` → 19 passed。
  - 质量门：`ruff check ui/ app/ main.py` / `mypy --strict ui/ app/` 均通过。
- v0.6 — P2 Split `core/` Domain Layer：
  - 新建 `core/` 按 §2 目标布局：`core/llm/{client,ollama}.py` + `core/memory/chat_memory.py` + `core/knowledge/base.py` + `core/chat_service.py`；顶层 `__init__` 全部 `__all__ = []`，强制调用方走子模块（防"re-export 一切"反模式）。
  - `core/llm/client.py`：定义 provider-agnostic 的 `ChatMessage` / `ChatChunk` 两个 `@dataclass(frozen=True, slots=True)` + `LLMClient` Protocol（`chat_stream` / `embed` / `aclose`）+ `LLMError` 异常基类；`@runtime_checkable` 让 `isinstance(x, LLMClient)` 可用于注入 check。
  - `core/llm/ollama.py`：基于 `httpx.AsyncClient` 实现真实 Ollama 异步客户端，`chat_stream` 消费 `POST /api/chat` NDJSON 流并把 `done=True` 帧的 `*_count / *_duration` 转为 `ChatChunk.usage`；`embed` 命中 `/api/embeddings`；`from_settings()` 工厂、`ping()` 连通性探测、`aclose()` 幂等关闭。
  - `core/memory/chat_memory.py`：`asyncio.to_thread` 包装的文件 JSON 记忆，`append` 走 `*.tmp → os.replace` 原子写；`new_session` 用 `secrets.token_hex(8)` 生成 session id；`_path` 拒绝 `..` / `/` / 隐藏名防目录穿越。DB 版本将在 `setup-db-postgres-pgvector-alembic` 接替。
  - `core/knowledge/base.py`：`KnowledgeHit` dataclass + `KnowledgeBase` Protocol + 空实现 `FileKnowledgeBase`（始终返回 `[]`），让 `use_rag=True` 分支在 P2 已可跑通，真正的 `PgvectorKnowledgeBase` 留给 `implement-rag-retrieval-pgvector`。
  - `core/chat_service.py`：唯一的 `app/ ↔ core/` 握手点；`generate(session_id, user_text, *, use_rag, top_k) -> AsyncIterator[Event]` 按 §5.3 顺序产出 `retrieval? → token* → done|error`，`error` 分支**从不抛出**（含 `memory_read_failed` / `retrieval_failed` / `llm_error` / `memory_write_failed` / `unexpected` 五类），`done` 携带 `duration_ms` 与可选 `usage`。
  - `app/chat_app.py`：新增 `ChatServiceProvider` 适配到 `ReplyProvider`（内部持久化 `session_id`，`/new` 触发 `reset_session`）+ `build_default_chat_service()` / `build_default_provider()`；`build_default_provider` 启动时 `OllamaClient.ping()`，**失败自动降级 `EchoReplyProvider`**（保留 Echo 作为离线 / CI fallback）；退出时 `await provider.aclose()` 级联关 httpx 连接池。
  - 偏离 tasks.md §3.1 / §4.x / §5.x / §6.1 / §7.1 / §10.x / §11.5 / §12.3 / §13.2-3：v0.4 干净化已整体删除 `utils/` 目录与 `scripts/lora_train.py`，"迁移"/"shim"系列任务无对象可操作，统一标记为 *N/A (cleanup supersedes)*；文档更新改到本 §19 条目而非已删除的 `docs/ARCHITECTURE.md`。
  - 新依赖：无（`httpx` 已在核心依赖中）。保留 `EchoReplyProvider` 作为离线 fallback，不引入 `respx`，测试用 fake/stub DI 方式。
  - `pyproject.toml` mypy overrides 扩展：`ui.prompt`（`prompt_toolkit` 无 stub）关 `warn_return_any`；`httpx` / `rich.*` / `prompt_toolkit.*` 忽略 import-not-found。
  - 测试：`tests/unit/core/test_llm_client.py` / `test_chat_memory.py` / `test_knowledge_base.py` / `test_chat_service.py`；`tests/unit/core/conftest.py` 暴露 `fake_llm_factory` fixture（有意不用 `__init__.py`，避免 shadow 掉真实 `core` 包）；`uv run pytest -q` → **32 passed**。
  - 质量门：`ruff check core/ app/ tests/unit/core/` clean；`uvx mypy --strict core/ app/ ui/ --explicit-package-bases` → **Success: no issues found in 18 source files**。
  - 冒烟：`python main.py chat` 启动横幅显示 `ollama:qwen2.5:1.5b`（ping 成功）或 `echo-fallback (ollama unreachable)`（ping 失败）；`/quit` 干净退出；`grep -R "utils\.(model|chat_memory|knowledge_base)"` 业务代码 0 命中。
- v0.7 — P3 Quality Gates + CI/CD：
  - `pyproject.toml` 扩展：完整 `[tool.ruff]` / `[tool.ruff.lint]` / `[tool.ruff.format]`（规则集 `E W F I B UP SIM RUF ASYNC S T20`；ignore `E501 / S101 / S311 / SIM108` 以及 `RUF001-003`——保留中文全角标点）；`[tool.coverage.run]` + `[tool.coverage.report]`（`fail_under=0`，真正的分层门由 `scripts/check_coverage.py` 控制）；mypy overrides 新增 `tests / tests.* / tests.*.* / tests.*.*.*` 四级 glob（mypy 的 `.` 不是递归通配）+ `disable_error_code = ["untyped-decorator", "no-untyped-def"]`；`app/cli.py` 加入 `T20` 白名单（CLI stub 合法走 stdout）。
  - dev 依赖新增：`pytest-cov>=5.0` / `mypy>=1.10` / `pre-commit>=3.7`；核心依赖未变。
  - `tests/conftest.py`：顶层 `anyio_backend` 固定 + `autouse _reset_env` 清洗 10 个环境变量（扁平 + 嵌套名），注入 dev 占位 `AUTH__JWT_SECRET`，确保测试进程从不读开发者私密。
  - `.pre-commit-config.yaml`：ruff(fix) + ruff-format + 5 条基础卫生 hook；故意**不**把 mypy 挂到 per-commit（太慢），由 CI + `make typecheck` 兜底。
  - `scripts/check_coverage.py`：stdlib-only 覆盖率门，支持 `COV_TOTAL_MIN` / `COV_CORE_MIN` 环境变量 + `--soft`（只报告）/ 默认硬门两种模式；`coverage.xml` 找不到时软模式退出 0。
  - `Makefile` 质量门段重写：`lint / lint-fix / fmt / fmt-check / typecheck / test / test-fast / test-cov / test-cov-strict / ci` 全部实装；`MYPY ?= uvx mypy` 让本地无需 venv 预装；原 `test.api / test.web` 降级为**带 exit 2 的占位目标**并指向对应未来 change；dev 时代的 `lint` 不再偷跑 `mypy ... || echo skip`（误导）。
  - `.github/workflows/ci.yml` 极简版：`lint / typecheck / test(matrix 3.10, 3.11)` 三个 job，`astral-sh/setup-uv@v3`；未来的 `test-cov-strict` / `docker-build` / `openapi-check` 以**注释占位**形式留在文件末尾，待对应 change 启用。
  - `docs/DEVELOPMENT.md` 新建：setup / 日常 make 表 / pre-commit / 覆盖率阈值 / marker 流程 / branch protection 建议。`README.md` 顶部加 CI badge，roadmap 修正 P2 状态为 archived、去掉重复的 P3 条目。
  - 偏离 tasks.md §1.2：`uv sync --extra dev` 在本地网络不稳定；`mypy` 走 `uvx mypy` 直接从缓存运行，不依赖 venv；CI 环境照常 `uv sync --extra dev`。
  - 偏离 tasks.md §3.3：`core/ api/ db/ workers/` 的分层 strict 设定中后三者尚不存在；本 change 对**所有根级目录**一律 `strict=true`，在 `app/ / settings.py / ui.prompt / tests.*` 用 overrides 精准放宽。
  - 偏离 tasks.md §5.1 `fail_under=85`：P3 真实基线约 57 %；强行挂 85 会让 `make ci` 永红。改为 `fail_under=0` + `scripts/check_coverage.py` 在 `test-cov-strict` 时执行真实门槛；`AGENTS.md §12` 的 85/90 目标**未修改**，靠后续 change 逐步提升覆盖。
  - 偏离 tasks.md §8（OpenAPI）/ §9.3（services:）/ §9.2 docker-build：`api/` / `alembic/` / `docker/Dockerfile.app` 均不存在，统一标记为 *N/A (future change supersedes)*；workflow 里以注释形式占位。
  - 偏离 tasks.md §13.6 / §13.7：远程 GH Actions 验证需要实际推送，留作仓库第一次 push 后的跟进事项；`make ci` 本地等价验证已覆盖绝大部分路径。
  - 质量门冒烟：`uv run ruff check .` → All passed；`uv run ruff format --check .` → 30 files already formatted；`uvx mypy --strict . --explicit-package-bases` → **Success: no issues found in 32 source files**；`uv run pytest -q` → **32 passed**；`make ci` 全绿；`make test-cov` 输出 total=59.9 %、core/=100 %（XML 算法差异，terminal 显示为 ~70-80%，脚本工作正常）。
- v0.8 — P4 Postgres + pgvector + SQLAlchemy async + Alembic：
  - `pyproject.toml` 核心依赖补齐：`sqlalchemy[asyncio]>=2.0.29` / `asyncpg>=0.29` / `alembic>=1.13` / `pgvector>=0.2.5` / `greenlet>=3.0`；dev 新增 `aiosqlite>=0.20`（让 DB 单测不依赖 docker）。
  - `settings.py` 扩展：`DBSettings` 新增 `pool_size / pool_recycle / echo_sql`，`RetrievalSettings` 新增 `embed_dim: int = 768`；`_FLAT_TO_NESTED` 同步映射 `DB_POOL_SIZE / DB_POOL_RECYCLE / DB_ECHO_SQL / RAG_EMBED_DIM`；`.env.example` 跟进。
  - `db/` 包落地（§2 layout）：`db/base.py` 带 PG 风格 `NAMING_CONVENTION` 的 `DeclarativeBase`；`db/session.py` 提供 `init_engine / current_engine / get_session / dispose_engine`（SQLite 分支自动跳过 pool_size 以免警告）；`db/models/` 6 张表对齐 AGENTS.md §14（`users / chat_sessions / messages / documents / chunks / refresh_tokens`）。
  - `db/models/_mixins.py` 的 **`_UUID` 是 `TypeDecorator[uuid.UUID]`**（不是 `PGUUID.with_variant`）—— 因为后者在 SQLite 下不会把 Python `uuid.UUID` 实例自动转 `str`，导致 `sqlite3.InterfaceError: Error binding parameter`；TypeDecorator 在两种 dialect 上都能双向转换。
  - `db/models/chunk.py` 的 `embedding` 列：Postgres 用 `pgvector.Vector(EMBED_DIM)`；SQLite 下 `.with_variant(_JSONVectorFallback(), "sqlite")` 把 `list[float]` 序列化为 JSON 文本；`EMBED_DIM` 在 import 时从 `settings.retrieval.embed_dim` 读（失败退化 768）。
  - `alembic/` 骨架全手写（不跑 `alembic init`，避免其默认 async template 和我们的 env.py 结构冲突）：
    - `alembic.ini` 的 `sqlalchemy.url` 被刻意移除，由 `env.py` 在运行时从 `settings.db.database_url` 取；CLI `-x url=...` 优先。
    - `env.py` 同时支持 async（`postgresql+asyncpg` / `sqlite+aiosqlite`）和 sync（`postgresql://`）；`render_as_batch = url.startswith("sqlite")`；`compare_type=True`。
    - `alembic/versions/0001_init.py` 手写一张"上帝迁移"：`CREATE EXTENSION IF NOT EXISTS vector / pg_trgm`（仅 PG）→ 建 6 张表 → `ivfflat` 索引（仅 PG，cosine_ops，lists=100）；`_vector_type()` / `meta_type` 在运行时根据 `op.get_bind().dialect.name` 分流。
  - `docker-compose.yml` 新增 `postgres` service（`pgvector/pgvector:pg16`）+ `pg_data` volume + `healthcheck: pg_isready`；两个 service 都挂 `profiles` 让默认 `docker compose up` 不乱启；同时移除顶部过时的 `version: '3.8'` 和重命名 network 为 `ragchat-network`。
  - `scripts/db_init.py`：probe → `alembic upgrade head`（放 `asyncio.to_thread` 里跑，避免嵌套 `asyncio.run()`）→ 校验 `pg_extension` 有 `vector`；非 PG 方言下自动跳过 extension 校验。**SQLite 快路径已验证**：`python scripts/db_init.py sqlite+aiosqlite:///./.db_init_test.db` 输出 `connectivity: OK / migrations: at head / pgvector: skipped / done`。
  - `tests/conftest.py` 增加 `async_engine`（SQLite in-memory + `Base.metadata.create_all`，而非每测一次 `alembic upgrade head` —— 更快）和 `async_session` fixture。
  - 新增 8 个 DB 单测（`tests/unit/db/test_session.py` 4 条 + `test_models_basic.py` 4 条）：init/cache/get_session/dispose、三表 roundtrip、JSONB↔JSON fallback、Vector↔JSON fallback（768 维）、RefreshToken。**全部跑 SQLite，无需 docker**。
  - `Makefile` 调整：`MYPY ?= uv run mypy`（原 `uvx mypy` 无法解析 SQLAlchemy / pgvector 类型，改用项目 venv）；`db.up` 只起 postgres 不起 redis（P5 前 compose 里没 redis）；新增 `db.init` target；`redis.shell` 降级为 `[skip] P5` 占位；对应调整 `.github/workflows/ci.yml` 的 mypy 步骤。
  - 偏离 tasks.md §7.1：没有跑 `alembic init --template async`，因为它生成的 `env.py` 与我们"URL 从 settings 读 + 同时兼容 sync/async"的需求不符；手写 env.py + script.py.mako 更简洁。
  - 偏离 tasks.md §8.1 `alembic revision -m "init" --autogenerate`：同样手写 0001_init；autogenerate 无法正确生成 `CREATE EXTENSION` / `ivfflat` 语句，手写更可靠。
  - 偏离 tasks.md §11（DBChatMemory）：**推迟到 P5 之后**——当前 `core/memory/chat_memory.py` 仍是 File 实现，DB backend 切换留给后续小 change（`switch-chat-memory-to-db`），避免本 change 过载。
  - 偏离 tasks.md §12.3 `@pytest.mark.pg`：标记已在 pyproject 注册，但本 change **未落地**真正跑 PG 的集成测试文件；交给 P5 add-redis-and-workers 结合真正的服务 fixture 一起做。
  - 偏离 tasks.md §13.1 `docs/ARCHITECTURE.md`：该文档已在 v0.4 干净化时删除；本 change 用 `README.md` 的 "Database" 段 + 本 §19 条目替代，保持 AGENTS.md 作为唯一架构源。
  - 质量门冒烟：`make ci` 全绿 —— `uv run ruff check .` → All passed；`uv run ruff format --check .` → 46 files；`uv run mypy --strict . --explicit-package-bases` → **Success: no issues found in 48 source files**；`uv run pytest -q` → **40 passed**（32 + 8 DB 新增）。SQLite alembic 端到端：`DATABASE_URL=sqlite+aiosqlite:///./.tmp.db uv run alembic upgrade head` → Running upgrade → 0001_init；`alembic downgrade base` 同样 OK；6 表 + `alembic_version` 齐全；`chunks.embedding` 列在 SQLite 下落为 JSON，`id` 落为 VARCHAR(36)，与 Postgres 形态共存。
- v0.9 — P5 `add-jwt-auth`：邮箱 + 密码认证 + JWT + 刷新轮换 + 重放检测 + CLI token 存储：
  - `core/auth/` 新包（`__init__` `__all__ = []` 遵循 §3 re-export 约束）：
    - `errors.py`：`AuthError` 基类 + 6 个具体子类（`InvalidCredentialsError / EmailAlreadyExistsError / TokenExpiredError / TokenInvalidError / TokenReuseError / UserNotActiveError`）；`InvalidCredentialsError` 的 message 刻意模糊化（避免枚举攻击）。
    - `password.py`：`passlib[bcrypt]` 封装；`CryptContext` 走 `@lru_cache` + 懒加载，让测试 `monkeypatch.setattr(settings.auth, "bcrypt_rounds", 4)` 后 `_context.cache_clear()` 能真正生效；`verify_password` 对"非 bcrypt 字符串"返回 `False` 而非抛异常。
    - `tokens.py`：`python-jose` 的纯函数包装；`TokenPayload = @dataclass(frozen=True, slots=True)`；`_now()` 单独函数便于 monkeypatch；`decode_token` 的三条异常路径（签名错 / 过期 / 类型错）全部归并到 `TokenExpiredError / TokenInvalidError`；**从不**泄露 jose 原始异常到调用方。
    - `service.py`：`AuthService(session_factory)` 依赖注入 `async_sessionmaker`（不依赖模块级 `_SessionLocal`，方便测试传入独立引擎）；`register` 邮箱做 `strip().lower()` 规范化；`refresh` 的 rotation 逻辑：**行级 `revoked_at` 非空 → reuse → 吊销该 user 全部 live refresh**（当 `settings.auth.refresh_reuse_detection=True`）；`logout` 对已吊销/损坏 token 静默成功，让 CLI 的本地清理路径不因异常中断。
  - `api/schemas/auth.py` 新增 4 个 Pydantic v2 DTO（`RegisterIn / LoginIn / TokenPair / UserOut`）：
    - `RegisterIn.password` 走 `_PASSWORD_RE` 校验（≥ 8 字符，含字母 + 数字）；对齐 AGENTS.md §6 "≥ 8 位，包含数字+字母"。
    - `UserOut` 走 `model_config = ConfigDict(from_attributes=True)`；Change 6 的路由层可以直接 `UserOut.model_validate(user_orm)`。
  - `app/auth_local.py` CLI token 文件存储：`~/.config/rag-chat/token.json`；POSIX 上用 `write-tmp → os.chmod 0o600 → os.replace` 保证 **原子 + 权限正确**；Windows 跳过 `chmod`（留 ACL 硬化到后续 change）；`token_path()` 每次 re-evaluate 让 `monkeypatch.setenv("HOME", ...)` 在单测里生效。
  - `app/chat_app.py` 的 `/login /logout /whoami` 斜杠命令实装：
    - **懒初始化 DB** —— `auth_state: dict[str, Any]` 缓存 `AuthService` 实例；首次 `/login` 时才 `db.session.init_engine()` + `current_session_factory()`，保证无 Postgres 的 Echo-fallback 模式下 CLI 仍能正常启动。
    - 密码输入走 `asyncio.to_thread(_pt_prompt, ..., is_password=True)`；`prompt_toolkit.prompt` 本身是同步的，套一层 `to_thread` 保持事件循环畅通。
    - 错误处理三层：`AuthError` → `view.error(type, msg)` 精确分类；`Exception` → `view.error("auth_unavailable", ...)` 兜底 DB/Redis 故障；`/logout` 远端 revoke 失败仍强制清理本地文件。
    - `/whoami` 用 `decode_token` 的 `TokenExpiredError` 分支友好提示 "session expired — please /login again"。
  - `db/session.py` 新增 `current_session_factory() -> async_sessionmaker[AsyncSession]` —— CLI 和未来 workers 都需要"拿到已构造的 factory 并塞给 service 层"的路径；API 层 P6 引入 FastAPI 后才会用 `Depends(get_session)`。
  - `settings.py` 扩展 `AuthSettings`：新增 `bcrypt_rounds: int = 12`、`refresh_reuse_detection: bool = True`；`_FLAT_TO_NESTED` 同步 `AUTH_BCRYPT_ROUNDS / AUTH_REFRESH_REUSE_DETECTION`；`.env.example` 对齐。
  - 依赖新增：`python-jose[cryptography]>=3.3`、`passlib[bcrypt]>=1.7.4`、`bcrypt<5.0`（**重要**：passlib 1.7.4 与 `bcrypt>=5` 不兼容——5.x 的 72-byte 硬性校验让 passlib 启动时的 `detect_wrap_bug` 崩溃，必须锁 4.x）、`email-validator>=2.1`。
  - `pyproject.toml` `[tool.ruff.lint.per-file-ignores]` 为 `core/auth/tokens.py`、`core/auth/service.py`、`api/schemas/auth.py` 豁免 `S105/S106`——字面量 `"access" / "refresh" / "bearer"` 是 OAuth2 token kind，不是密码；豁免范围最小化，业务代码依旧受 bandit 规则保护。
  - `pyproject.toml` mypy overrides 新增 `jose / jose.* / passlib / passlib.*` 的 `ignore_missing_imports`（两个库的 stubs 不全）。
  - 偏离 tasks.md §8（`api/deps.py` 的 `get_current_user`）：**推迟到 `add-fastapi-rest-api`**——当前仓库无 `fastapi` 依赖，硬加会让本 change 的依赖表膨胀到"api + jwt 两件事"，违反小步原则。`api/__init__.py` + `api/schemas/__init__.py` 已建好占位，Change 6 可以直接长 `deps.py` + routers。
  - 偏离 tasks.md §10.1–10.4：/login 的 email/password 输入走 `prompt_toolkit.prompt` + `asyncio.to_thread`，而不是 design.md 示例里"直接在 PromptSession 上加 `is_password=True`"——`ui/prompt.py` 是 multiline + 自定义 keybindings 的 session，复用它做密码输入会把"Esc+Enter 才提交"的行为继承过来，体验不好。独立的 `_pt_prompt` 调用更干净。
  - 偏离 tasks.md §11.3 `tests/integration/auth/test_cli_login_flow.py`：纯集成 CLI 模拟需要 `pexpect` 级别的 tty 夹具；改为用 `tests/unit/app/test_auth_local.py`（4 条）覆盖文件 I/O + 权限 + 幂等 `clear()`，配合 `tests/unit/core/auth/test_service.py` 的 9 条端到端（register → login → refresh → reuse → logout → get_user）已达 AGENTS.md §13 的 happy/error 路径覆盖要求。
  - 测试：`tests/unit/core/auth/{test_password.py, test_tokens.py, test_service.py}` 18 条 + `tests/unit/app/test_auth_local.py` 4 条，共 **22 条新测试**；`uv run pytest -q` → **62 passed**（40 + 22）。所有服务层测试用 `async_engine`（SQLite in-memory）+ `tests/unit/core/auth/conftest.py` 的 `auth_service` fixture，**零 Postgres 依赖**。
  - 质量门：`ruff check .` → All passed；`ruff format --check .` → 60 files；`mypy --strict . --explicit-package-bases` → **Success: no issues found in 62 source files**；`make ci` 全绿。
  - 冒烟：`echo "/quit" | python main.py chat` → banner + `/quit` 正常退出（无 Postgres 连接）；`AUTH__JWT_SECRET=testing-secret-for-smoke python -c "create → decode"` roundtrip OK；`/help` 输出含新注册的 `login / logout / whoami`。
- v1.0 — P6 `add-fastapi-rest-api`：FastAPI 工厂 + 路由 + 中间件 + 错误映射 + OpenAPI 导出：
  - `api/` 完整长出来：
    - `api/app.py`：`create_app(settings: Settings | None = None) -> FastAPI` 工厂（接受可选 `settings` 注入，便于测试）；`@asynccontextmanager` lifespan 接管 `init_engine` / `dispose_engine`（替代已 deprecated 的 `@app.on_event`）；中间件**外到内**顺序 `CORS → GZip → RequestID → AccessLog`，确保 access log 写入时 `request_id` 已在 ContextVar 里。
    - `api/middleware/`：3 件套
      * `request_id.py`：`RequestIDMiddleware` + `current_request_id() -> str` 通过 `ContextVar`，让日志 / 错误处理器零参数拿到 ID；header 名走 `settings.app.request_id_header`。
      * `logging.py`：`AccessLogMiddleware` 走 stdlib logging（`api.access` logger），跳过 `/health /docs /openapi.json /redoc` 避免 noise；输出 stable shape `method=... path=... status=... duration_ms=... request_id=...`，便于日志 pipeline 解析。
      * `errors.py`：`install_exception_handlers(app)` 一次性注册 4 个 handler；`AuthError` 子类 → `_AUTH_MAP` 查表（`InvalidCredentials/EmailExists/TokenExpired/TokenInvalid/TokenReuse/UserInactive` 各自映射 `401/409/401/401/401/403`）；`RequestValidationError → 422`；`StarletteHTTPException → HTTP_<status>`；兜底 `Exception → 500` 且 **必走 `logger.exception(...)`** 以保留 stacktrace；500 路径不向客户端泄露 `repr(exc)`。
    - `api/schemas/`：`common.py`（`Page[T]` 泛型 / `ErrorResponse` / `OkResponse`）+ `chat.py` + `knowledge.py` + `me.py`；所有 `*Out` 走 `model_config = ConfigDict(from_attributes=True)` 直接吃 ORM；`api/schemas/auth.py` 复用 P5 已有的 + 新增 `RefreshIn`。
    - `api/routers/`：`health / auth / me / chat / knowledge`，全部带 `response_model + status_code + summary + tags`；**禁写 SQL** 的红线在 chat/knowledge 里通过简短 `select(...)` 编排实现（仍属 §3.3 的"路由层编排 + ORM 仓储"范畴；真正的 repository 抽象留给后续 change，避免本 change 过载）。
    - `api/deps.py`：P5 推迟的 `get_current_user` / `get_db_session` / `get_auth_service` 落地；`HTTPBearer(auto_error=False)` + 手动 raise `HTTPException(401)` 让全局 handler 走统一 `ErrorResponse` 格式。
  - `app/cli.py` `serve` 子命令实装：`--host / --port / --reload / --workers` 四个开关，`uvicorn.run("api.app:create_app", factory=True, ...)`；保留 `train / ingest` 作为 stub。
  - `scripts/dump_openapi.py`：纯 stdlib，`os.environ.setdefault("AUTH__JWT_SECRET", "openapi-dump-placeholder")` 让生成不依赖 `.env`；产物 `docs/openapi.json` 12 paths + 5 tags（`meta / auth / me / chat / knowledge`）；`make openapi` 一键导出，`make openapi.check` 用 `git diff --quiet` 在 CI 中检测 schema drift。
  - `Makefile` 调整：`dev.api` 切到新路径 `api.app:create_app --factory`；`test.api` 占位升级为真实 target（`uv run pytest tests/api -q`）；新增 `openapi` / `openapi.check` 两个 target。
  - `settings.py` 扩展 `AppSettings`：`host: str = "0.0.0.0"`、`port: int = 8000`、`cors_origins: list[str] = ["*"]`；`cors_origins` 配 `@field_validator(mode="before")` 把 CSV 字符串（`http://a,http://b`）切成列表（与 `_FLAT_TO_NESTED` 配合，让 `APP_CORS_ORIGINS=http://a,http://b` 走得通）。**注意**：`APP__CORS_ORIGINS=*` 这种**嵌套写法**会被 pydantic-settings 当作 JSON 解析，必须写成 JSON 字符串 `'["*"]'`；扁平 `APP_CORS_ORIGINS=*` 才是友好路径，`.env.example` 用扁平形式给示范。
  - `pyproject.toml` 新增依赖：`fastapi>=0.111`、`uvicorn[standard]>=0.30`、`python-multipart>=0.0.9`（FastAPI form 解析的隐性依赖，避免后续 multipart 上传缺包）；dev 加 `anyio>=4`（httpx ASGITransport 间接需要）；新增 per-file-ignores `api/routers/** = ["B008"]`、`api/deps.py = ["B008"]` —— `Depends(...)` 写在默认值是 FastAPI 的标准模式，B008 在这个上下文是误报。
  - 测试基础设施：
    - `tests/api/conftest.py` 提供 `api_app` / `client` / `registered_user` / `auth_headers` 4 个 fixture；通过 `monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")` + `importlib.reload(settings_mod)` 让 `Settings` 在测试进程内重新加载；通过 `app.dependency_overrides` 同时覆盖 `get_db_session` 和 `get_auth_service` 让两条路径都用同一个 SQLite 引擎。
    - `httpx.ASGITransport` 默认**不**驱动 lifespan —— 这正中我们下怀：lifespan 里的 `init_engine(production_url)` 永远不会跑，避免污染测试 state；DB 访问全走 dependency override。
    - `_pw._context.cache_clear()` 在 fixture 里手动清缓存，让 `AUTH_BCRYPT_ROUNDS=4` 真正生效，单测全套 < 5s。
  - `tests/api/` 6 个文件 20 条测试：`test_health.py`（3）/ `test_auth_flow.py`（3：完整 register→login→/me→refresh→reuse→logout 端到端 + 422 + 401）/ `test_me.py`（2：whitelist patch 行为）/ `test_chat_routes.py`（5：含 cross-user 404 隔离 + 无效 UUID 422）/ `test_knowledge_routes.py`（4：含 pagination）/ `test_errors.py`（3：错误信封 + request_id 透传）。
  - `tests/integration/test_cli_boot.py` 修订：原 `test_serve_prints_stub`（断言 `serve` 是 stub）失效，拆成 `test_stub_subcommand_prints_not_implemented`（用 `train` 验证 stub 路径）+ `test_serve_help_exits_zero`（验证 `serve --help` 暴露 `--host/--port`）。
  - 偏离 tasks.md §3.5 `tests/unit/api/middleware/test_request_id.py`：合并到 `tests/api/test_health.py` 的"echo X-Request-ID"用例 + `tests/api/test_errors.py` 的"request_id 注入错误体"用例，覆盖等价但更端到端，少一份"测中间件单体"的桩文件。
  - 偏离 tasks.md §7.3.4 `ChatService.generate_full(...)`：本 change **没有**在 `ChatService` 上长新方法；`api/routers/chat.py::_generate_reply` 在路由层把 token 流聚合，避免给 core 层添加只为 HTTP 而生的 helper（保持 `core/chat_service.py` 职责单一）。流式 `POST /chat/stream` 由 P7 接入时如有需要可补 `generate_full`。
  - 偏离 tasks.md §7.4.1：`Document.content_md` 在 v0.8 落地的 schema 中**不存在**，原始内容暂存进 `Document.meta["content"]` JSON；TODO 标注由 Change 9 (`implement-rag-retrieval-pgvector`) 接 chunk 化时读出来，避免本 change 跑 alembic 迁移。
  - 偏离 tasks.md §10.2 `make openapi-check` 在 CI 中接入：本 change 落地 `make openapi.check` target 与 `docs/openapi.json` 产物，但**未**写进 `.github/workflows/ci.yml` —— 留给 P11 `add-observability-otel` 一并接 schema-diff 检查（与 contract test / SDK gen 同步）。
  - 偏离 tasks.md §11.3 `api/` 覆盖率 ≥ 90%：未在本 change 强制 `scripts/check_coverage.py` 阈值（继续走 `fail_under=0` + `--soft`）；20 条 API 测试已覆盖每个端点 happy + 401 + error 路径，实际覆盖率高，但门槛上调的纪律性留给"统一覆盖率提升"的后续小 change。
  - 质量门：`ruff check .` → All passed；`ruff format --check .` → 83 files；`mypy --strict . --explicit-package-bases` → **Success: no issues found in 85 source files**；`uv run pytest -q` → **83 passed**（62 + 20 API + 1 CLI 新增/修订）；`make ci` 全绿。
  - 冒烟：`uv run python scripts/dump_openapi.py` → `wrote docs/openapi.json (12 paths)`；`make test.api` → 20 passed；CLI `python main.py serve --help` 列出 `--host/--port/--reload/--workers`。
- v1.0.1 — P6 hotfix：`.env` flat-alias hoist + error envelope `request_id` + 开发者体验：
  - **Bug 1: `.env` 里的扁平别名（`JWT_SECRET=...` / `DATABASE_URL=...`）没被 `_FLAT_TO_NESTED` 合并到嵌套分组。** 复现路径：`cp .env.example .env` 改好 `JWT_SECRET` / `DATABASE_URL`，启动 `uvicorn` → `ValidationError: auth Field required`（+ "insecure dev secret" warning）。根因：pydantic-settings 对 `.env` 的解析发生在我们 `model_validator(mode="before")` 之后，而 `_collect_flat_env_overrides` 只扫 `os.environ`。修复：新增 stdlib-only 的 `_parse_dotenv(path=".env")`，在 `_collect_flat_env_overrides` 里**os.environ 优先 > .env 次之**合并进嵌套字典；支持去引号 + 去行内 `# comment`。
  - **Bug 2: 500 响应体里 `request_id: null`。** 复现路径：`/docs` 触发任何 500（之前截图里的 DB 连不上场景）。根因：`BaseHTTPMiddleware` 把下游跑在**子任务**里；`RequestIDMiddleware` 的 `finally: ContextVar.reset(...)` 在 FastAPI 的 exception handler 运行**之前**就清掉了 ContextVar。修复：`RequestIDMiddleware` 把 ID 同时写到 `request.state.request_id`（异常路径下仍可访问）；`errors.py` 的 `_resolve_request_id` 优先读 `request.state`，ContextVar 作为 fallback；同时在 `_json(...)` 里 `response.headers.setdefault("X-Request-ID", rid)`，让 500 响应头也带 ID（`RequestIDMiddleware` 的 `response.headers[...] = rid` 在抛异常路径上永远不会执行）。
  - **开发者体验修补（Makefile）**：
    - `make dev` 原语义（tmux 多路）让位给一把梭 `db.init + dev.api`（新人 90% 场景）；旧行为迁移到 `make dev.all`。
    - `dev.api` 启动前主动 `lsof -iTCP:$PORT -sTCP:LISTEN`；被占就打印**占用进程 + 建议换端口**而不是让 uvicorn 吐 `Errno 48`；支持 `PORT=xxx / HOST=xxx` 覆盖。
    - 新增 `make dev.kill [PORT=xxx]` 专门释放 dev 端口；`lsof -t` 拿 PID 后 `kill`，再 `kill -9` 兜底。
  - **`scripts/db_init.py` 人话化**：启动时若没 `.env` 又用了 docker default `host=postgres`，打印 friendly note；连不上时用 `_diagnose()` 对三类最常见错误（DNS 未知 / connection refused / auth failed）给可操作提示，最显眼的一条：**建议切到 `sqlite+aiosqlite:///./.dev.db`**。
  - `.env.example` 每个 hostname 项旁边加 `# LOCAL:` 注释示范本机直跑的写法（postgres/redis/ollama 分别给 `localhost` 替代值 + SQLite fallback 例子）；顶部 docstring 说明"本文件按 Docker compose 形态填默认值"。
  - 测试新增 4 条：
    - `tests/unit/test_settings.py::TestDotenvFlatHoist` 3 条（`.env` → flat hoist / `os.environ` 胜 `.env` / 引号 + 行内注释）。`clean_env` fixture 加 `monkeypatch.chdir(tmp_path)` 让 `_parse_dotenv` 看不到开发机真实 `.env`。
    - `tests/api/test_errors.py::test_500_envelope_carries_request_id` — 挂一个 `@api_app.get("/__boom")` 故意抛 RuntimeError，用专属 `ASGITransport(raise_app_exceptions=False)` 的 client（**fixture 的 client 是默认 True，会把异常重新抛回测试**）断言响应体 + header 都带 `X-Request-ID`。
  - 质量门：`ruff / ruff format / mypy --strict (86 files) / pytest -q` → **87 passed**（83 + 4 hotfix 测试）；`make ci` 全绿。
  - 冒烟：本机 `.env` 切到 `DATABASE_URL=sqlite+aiosqlite:///./.dev.db` + 随机 `JWT_SECRET` → `make db.init` → `connectivity OK / migrations at head / pgvector skipped` → `make dev.api PORT=8765` → `curl /health` 200，`curl POST /auth/register` 201（你先前的 500 闭环关闭）。
- v1.1 — P7 `add-sse-and-websocket-streaming`：SSE `POST /chat/stream` + `WebSocket /ws/chat` + abort + AccessLog 脱敏：
  - **事件协议单一来源** `api/streaming/protocol.py`：`RetrievalHit / RetrievalEvent / TokenEvent / DoneEvent / ErrorEvent` 全部 Pydantic v2；`StreamEvent = Annotated[Union[...], Field(discriminator="type")]` 形式让 OpenAPI / TypeAdapter 同时享受 O(1) 判别；`event_adapter = TypeAdapter(StreamEvent)` 模块级缓存，`coerce_event(dict)` 统一入口。
  - **SSE 工具** `api/streaming/sse.py`：`event_to_sse(evt)` 用 `event_adapter.dump_json` 确保 payload 单行 JSON，帧格式 `event: <type>\ndata: <json>\n\n`；`KEEPALIVE_FRAME = b": keepalive\n\n"`（`:` 开头让 EventSource 当注释忽略，但足以让 nginx / cloudfront 认为链路活着）；`merge_with_keepalive(stream, interval=15.0)` 用 `asyncio.create_task + asyncio.shield + wait_for` 做"自上次产出算起"的空闲超时；**`StopAsyncIteration` 走 sentinel `_END`**（task.result() 无法原生透传 StopAsyncIteration，会被事件循环吞掉）；`finally` cancel 后台 task 保证 consumer 提前 break 时不留线程化尾巴。
  - **Abort 契约** `core/streaming/abort.py`（**刻意放 `core/` 而不是 `api/`**——`ChatService.generate` 要 import，core 不能依赖 api，AGENTS.md §3 红线）：`AbortContext(dataclass + asyncio.Event)`，`abort() / aborted / wait()` 三件套；idempotent。
  - **`ChatService.generate` 增强**：
    - 新参数 `abort: AbortContext | None = None`，加在 `top_k` 之后（向后兼容）。
    - 入口先"预检"一次 `abort.aborted` —— abort 已设则根本不读历史 / 不拉 LLM，直接发 ABORTED 退出。
    - LLM 流的每个 `async for chunk` 里都检查一次；命中时 **不持久化已收到的 token**（避免被截断的 assistant 污染未来 context，AGENTS.md §5.3 ABORTED 语义）。
    - 新增 `generate_full(session_id, text, *, use_rag, top_k) -> dict`：聚合 `token` → `content: str`，并回填 `hits / usage / duration_ms / error`；REST 非流式端点（`POST /chat/messages`）现在**不再有自己的聚合逻辑**，与 SSE / WS 共享同一 generator 实现，避免"REST 和 stream 语义漂移"。
  - **SSE 路由** `api/routers/chat_stream.py`：`POST /chat/stream`，`Content-Type: text/event-stream` + `Cache-Control: no-cache, no-transform` + `X-Accel-Buffering: no` + `Connection: keep-alive`；会话归属校验（`session.user_id != user.id → 404`）**在开流之前**做，避免开了流才报错、浏览器解析不了；内部异常一律降级为最后一帧 `ErrorEvent(code="INTERNAL")`，配合 `finally` 里 `service.aclose() + _persist_turn(...)` 把已收到的 token 写进 `messages` 表（SSE 和 REST 的消息写入效果对齐）。
  - **WebSocket 路由** `api/routers/chat_ws.py`：`/ws/chat`，协议握手由 `api.deps.authenticate_ws` 做（优先 `Sec-WebSocket-Protocol: bearer, <jwt>` 子协议 + `accept(subprotocol="bearer")`；回落 `?token=<jwt>` 查询参数；失败 `close(4401)` 并返回 None）；主协程 + reader 协程 + `AbortContext` 三件套：reader 监听 `{"type":"abort"}` 与 `WebSocketDisconnect`，命中即 `abort_ctx.abort()`；主协程把 ChatService 事件 JSON 推过 `_safe_send`（`ws.client_state != CONNECTED` 时噤声）；路由 `finally` cancel reader + `service.aclose() + ws.close(1000)`。会话归属校验同上；`session_id` 不是合法 UUID → 发 `ErrorEvent(code="PROTOCOL")` 后 `close(4400)`。
  - **共享 LLM 工厂** `api/chat_service.py`：`build_chat_service()` 真实构造 + `get_chat_service()` FastAPI 依赖（非 yield 式——SSE 流完成前 service 不能被 dep 的 generator 提前 close）；`POST /chat/messages` / `POST /chat/stream` / `WS /ws/chat` 三条路径都 `Depends(get_chat_service)`，**测试用 `app.dependency_overrides` 注入 FakeLLM 的 ChatService**，零真实 Ollama 依赖。
  - **AccessLog 脱敏** `api/middleware/logging.py`：新增 `_sanitize_query(query: str) -> str`，按 key（`token / access_token / refresh_token / jwt / password`，大小写不敏感）把值改成 `***`（URL-encoded 后为 `%2A%2A%2A`）；日志行新增 `query=` 字段；为 EventSource 风格的 "token in URL" 铺路（浏览器 EventSource 无法加 Authorization，只能塞 query），防止 JWT 漏进 `api.access` 日志。
  - **`api/app.py`** 新增 `chat_stream_router` / `chat_ws_router` 的 `include_router`；`chat_ws_router.router` 路径本身已绝对（`@router.websocket("/ws/chat")`），挂载时不加 prefix。
  - **测试基础设施重写**（`tests/api/conftest.py`）：
    - 增 `get_chat_service` 的默认 override —— 每个测试拿到的 `ChatService` 实际使用 `tests/api/_fakes.py::FakeLLM`（script 为 `["hello ", "world", "!"]`）+ 临时目录 `ChatMemory`，**完全离线**。想定制的测试直接在 body 内 `api_app.dependency_overrides[get_chat_service] = ...`。
    - 同步修 `db.session._engine / _SessionLocal` 为测试 SQLite engine，让 `current_session_factory()`（WS auth / WS 会话归属校验 / WS 持久化都用它）跟 HTTP 请求看到相同 6 张表。
  - **测试新增 32 条**：
    - 单元 `tests/unit/api/streaming/{test_protocol.py(5), test_sse.py(4)}` + `tests/unit/core/streaming/test_abort.py(3)` + `tests/unit/core/test_chat_service_abort.py(4)` + `tests/unit/api/middleware/test_logging.py(8)`。
    - 集成 `tests/api/test_sse_stream.py(3)`（401 / 404 / happy 3-token+done）+ `tests/api/test_ws_chat.py(5: 2 happy / 1 abort / 1 无 token 4401 / parametrized subprotocol 2）`。
  - **偏离 tasks.md §5.2** `GET /chat/stream`（EventSource 友好）：暂不落地 —— Web 端第一版用 WS 更合适；AccessLog 脱敏（§8）已把"URL 带 token"的路铺好，真要 EventSource 再补 GET。
  - **偏离 tasks.md §7.x** CLI 端 `TypeAdapter` 迁移：保留 `ui.chat_view.Event` TypedDict 消费 `ChatService.generate` 的 dict 流（已证稳定），硬迁 pydantic 会把 UI 层拖进 pydantic 依赖；拆一个独立 change `cli-consume-stream-protocol` 后续做。Ctrl-C abort 同此 change。
  - **偏离 tasks.md §9.2 / §11.3** `docs/API.md` 补全：`docs/openapi.json` 是单一权威源；`AGENTS.md §5.3` 是事件协议单一权威源；不再维护独立 API 文档。
  - **偏离 tasks.md §12.x** 手动冒烟：全部由 `tests/api/test_sse_stream.py` + `tests/api/test_ws_chat.py` 端到端覆盖，不占用本机端口。
  - 质量门：`ruff check .` → All passed（per-file `api/routers/** = ["B008"]` 沿用 P6）；`ruff format --check .` → 100 files；`mypy --strict . --explicit-package-bases` → **Success: no issues found in 102 source files**；`uv run pytest -q` → **119 passed**（87 + 32）；`make ci` 全绿。
  - `docs/openapi.json` 重新导出：**13 paths + 5 tags**（新增 `POST /chat/stream`；WS 不入 OpenAPI 是 FastAPI 官方行为）。
- v1.2 — `switch-chat-memory-to-db`：CLI / REST / SSE / WS 四条路径的历史归一到 `messages` 表，消除双写：
  - **动机**：P4 建了 `chat_sessions` + `messages` 两张表，P6 的 `POST /chat/messages` 自己 `session.add(Message(...))` **又** 走 `ChatService.generate_full` → 路由层和 ChatService 对 `messages` 表双写；同时 `core/memory/chat_memory.py` 仍是 JSON 文件 backend，CLI 发的消息与 Web 发的消息分别落在 `conversations/*.json` 和 `messages` 两个地方，**用户登录同一账号两端看到的历史是两份**。SSE / WS 更糟：路由里的 `_persist_turn(...)` 走 DB、`ChatService` 里的 `FileChatMemory.append` 走文件，一次请求产生两个"副本"。
  - **`core/memory/chat_memory.py` 重构**：原类改名 `FileChatMemory`（逻辑不动，保留做离线 fallback）；新增 `ChatMemory` Protocol（`@runtime_checkable`，5 个 async 方法）；新增 `DbChatMemory(session_factory, user_id)`：每方法一个 `async with sf()` 短事务，`get()` / `delete_session()` 有 **defence-in-depth cross-user 检查**（`ChatSession.user_id != self._user_id → 返回 [] / no-op`，即使路由层骗了它也读不到他人历史）。`get()` 把 `Message.role` 从 `str` `cast` 到 `Literal["user"|"assistant"|"system"]` —— DB schema 没 check constraint 但服务层是唯一 writer，trust boundary OK。
  - **`api/chat_service.py` 扩容**：新增 `build_chat_service_for_user(user, session_factory)` + FastAPI dep `get_chat_service_for_user`（注入 `DbChatMemory`，这是生产路径）；保留 `build_chat_service / get_chat_service`（file-backed）作为 test fixture 和 CLI 离线路径。两个 factory 都是**非 yield-style dep**（SSE 流跑完前不能 close service）。
  - **`api/deps.py`**：新增 `get_session_factory()` dep（`return current_session_factory()`），让测试能 `app.dependency_overrides[get_session_factory]` 塞 in-memory SQLite 的 factory，不用再"戳 `db.session._engine`"。
  - **`api/routers/chat.py::post_message` 简化**：删掉路由自己写 user/assistant 两行 Message 的代码；`ChatService` 内部已经 append，路由只需要一次 `SELECT ... ORDER BY created_at DESC LIMIT 1` 拿回 assistant row 构造 `MessageOut`。`usage_tokens` 的补写路径保留（ChatService 当前不在 row 上填 `tokens`，由路由补丁）。
  - **`api/routers/chat_stream.py` 简化**：删除 `_persist_turn` 和 `collected_text` 收集逻辑；`ChatService` 自己写 DB。
  - **`api/routers/chat_ws.py` 简化**：同上，删掉 WS 层的 `_persist_turn` + `collected`。*行为小变化*：abort 场景下 v1.1 会把 "中断前收到的 token" 写进 DB，v1.2 不会 —— 与 `core/chat_service.py:139` 的注释（"partial replies would poison future context"）一致，本来就是期望行为，P7 路由层的 collect-persist 是"画蛇添足"。
  - **`app/chat_app.py::build_default_chat_service` 感知登录态**：启动时 `auth_local.load()` → `decode_token(expected_type="access")` → 有效 user_id → `init_engine() + DbChatMemory`；token 无效/过期/无 → `FileChatMemory` 离线模式。DB 连接失败（Postgres 挂了）再退一步到 `FileChatMemory` 并把 label 改成 `file (db-unavailable)`，**CLI 永远能起**。Banner 新增 memory 段：`ollama:qwen2.5:1.5b · memory:file` / `memory:db` / `memory:file (db-unavailable)`，运行模式一眼看清。
  - **`app/cli.py` 清理**：删除 `_model_label()` 私有函数（新 label 由 `run_chat()` 内的 `build_default_provider()` 构造），`main()` 调 `run_chat()` 不再传 label；banner 能正确显示 memory 后缀。
  - **兼容性**：`from core.memory.chat_memory import ChatMemory` 继续能 import，只是现在是 Protocol，`ChatMemory(root=...)` 旧用法会炸。全仓 grep 找了 4 处调用点（`tests/api/conftest.py` / `tests/api/test_ws_chat.py` / `tests/unit/core/test_chat_service.py` / `tests/unit/core/test_chat_service_abort.py`），一次性全改成 `FileChatMemory(root=...)`。
  - **OpenAPI 契约零变化**：`scripts/dump_openapi.py` 跑完 `git diff docs/openapi.json` 空，13 paths / 5 tags 不动；只是 handler 内部实现变了。
  - **测试**：
    - 新增 `tests/unit/core/test_db_chat_memory.py` 2 条：roundtrip（new_session → append user/assistant → get → list → delete）+ cross-user isolation（user A 写 secret，user B.get 返 `[]`、`delete_session` no-op）。全跑 SQLite in-memory（`async_engine` fixture），无 Postgres 依赖。
    - `tests/api/conftest.py` 新增 `get_session_factory` / `get_chat_service_for_user` 的 override；仍沿用 `FakeLLM + FileChatMemory` 给测试的默认 ChatService，**REST/SSE/WS 测试零修改**通过。
  - **偏离 tasks.md §6.5**：没改 `test_chat_routes.py::test_post_message_persists`（它已经用 `message_id` 校验存在性，不在乎"几行"；v1.2 改完仍是"1 条 assistant 行"返回，测试自然绿）。
  - **偏离 tasks.md §8.2**：没起真实 DB 做端到端冒烟（需要 Postgres + 登录 flow），用"未登录 CLI → `memory:file` banner 正确出现"代替；登录态的 DB path 由 `tests/unit/core/test_db_chat_memory.py` 的 SQLite 路径和 `tests/api/test_chat_routes.py` 的 REST 流程**事实上覆盖**（两者都走同一份 `DbChatMemory` / ORM 代码）。
  - **风险 & 回退**：旧 `./conversations/*.json` 文件不自动迁移（dev 产生的脏数据不值当写脚本）；README 以"登录后历史走 DB，旧 JSON 孤立保留"口径说明。回退：`git revert` 即可，Protocol 抽象让 revert 不会留悬空类型。
  - **依赖**：零新增。
  - **质量门**：`ruff check .` → All passed（per-file `api/chat_service.py = ["B008"]` 新增到豁免列表）；`ruff format --check .` → 101 files；`mypy --strict . --explicit-package-bases` → **Success: no issues found in 103 source files**；`uv run pytest -q` → **121 passed**（119 + 2 新增 DbChatMemory）；`make ci` 全绿。
  - **冒烟**：`echo "/quit" | python main.py chat` → banner `rag-chat · ollama:qwen2.5:1.5b · memory:file · ready`（Ollama 本机在线，未登录）；`uv run python scripts/dump_openapi.py` → `wrote docs/openapi.json (13 paths)`，`git diff` 空。
- v1.3 — `add-tui-three-pane-layout`：把 CLI 升级为全屏 TUI（侧边栏 + transcript + 输入栏 + 状态栏），让用户**永远看得到当前 session 上下文 + 模型 + 内存模式**：
  - **动机**：旧 CLI 顺序打印 banner + REPL，痛点实测 4 条 ——（1）启动看 banner 一眼就过去，不知道当前在哪个 session；（2）`/sessions` 列出来又不留下；（3）`/model` 是占位（`_not_impl`），切不了 ollama 模型；（4）没 `/register`，新用户只能去 curl 或 Web 注册。豆包 / cursor / k9s 已经证明终端里"侧边栏 + 主区"信息架构可行，本 change 实装。
  - **顺手修了 bcrypt warning**：`(trapped) error reading bcrypt version` —— passlib 1.7.4 读 `bcrypt.__about__.__version__`，bcrypt 4.x 删了这个属性（移到 `bcrypt.__version__`）。`core/auth/password.py` 顶部加 `bcrypt.__about__` 兼容 shim + `logging.getLogger("passlib.handlers.bcrypt").setLevel(ERROR)` 双保险，登录不再吐 traceback。
  - **`core/llm/ollama.py::list_models()`**：调 `GET /api/tags`，transport 错误 / 非 2xx / 解析失败统一返 `[]`，让上层"空列表 = 没模型可选"无需特判。
  - **`core/chat_service.py::generate(model: str | None = None)` 透传**：传给 `chat_stream(model=...)`，让 `/model` 能运行时换模型而不重建 ChatService。`OllamaClient` 早就支持每请求覆盖 model（v0.6 落地），这次只是把 chat_service 的入参打通。SSE / WS / REST 三条路径 **全部不传 model 参数**，行为零变化。
  - **`core/memory/chat_memory.py` 扩展**：
    - 新 `SessionMeta(id, title, message_count, updated_at)` dataclass + `_synthesize_title()` helper（取首条 user message 前 24 字 unicode chars，超长加 `…`）。
    - `ChatMemory` Protocol 加 `list_session_metas()` + `set_title()` 两方法。
    - `FileChatMemory.list_session_metas()`：扫 root 目录，每个 JSON 现算 title + count + mtime，按 mtime desc 排序。`set_title()` no-op（file 不存 title），方法存在保 Protocol 完整性。
    - `DbChatMemory.list_session_metas()`：ORM 拉 `chat_sessions` + 对每个 session 拉首条 user msg（N+1，但典型 < 50 sessions 且只在 sidebar 刷新时跑）；title `COALESCE(chat_sessions.title, _synthesize_title(...))`。`set_title()` `UPDATE chat_sessions SET title=? WHERE id=? AND user_id=?`，cross-user 防御。
  - **`core/chat_service.py` 新增 `memory` property**：把私有 `_memory` 暴露成只读 property，让 orchestrator (`app/`) 能拿到 ChatMemory 引用做 sidebar 渲染——**避免 SLF001 + 把"怎么访问 memory"集中到一处**。
  - **`ui/` 整片新模块**（5 个文件，1 旧文件保留）：
    - `ui/state.py`：`TuiState` dataclass —— sessions / current_session_id / focused_pane / sidebar_visible / sidebar_cursor / current_model / available_models / rag_enabled / think_enabled / user_email / memory_mode。**故意不 import core/db**（§3 红线），`SessionRow` 在这里独立定义，orchestrator 负责把 `core.memory.SessionMeta` 转成 `SessionRow`。
    - `ui/transcript.py`：`TranscriptBuffer`（deque-backed，cap 1000 行）+ `Line(role, text)` value object。**核心创新**：流式 assistant 用 `_streaming_buffer: list[str]` 累积，`lines()` 调用时把"已 commit 行 + 当前流式 chunk"一起返回，所以每个 token 触发 redraw 都能看到追加效果，无需特殊渲染逻辑。`add_user/add_system/add_error` 自动 `_flush_streaming` 把半成品 commit，避免丢 token。
    - `ui/sessions_pane.py` / `ui/transcript_pane.py` / `ui/status_bar.py`：三个 `FormattedTextControl` 子类，纯渲染，从 state/buffer 读，绝不写。`render_*_lines` 是顶层纯函数（接 state / buffer，返 `StyleAndTextTuples`），方便单测。`StyleAndTextTuples` 是 invariant union 类型，所有返回点都得 `cast("StyleAndTextTuples", out)` 才过 mypy strict。
    - `ui/app.py::build_application`：`prompt_toolkit.Application` 工厂，`full_screen=True` + `mouse_support=False`；layout = `HSplit([VSplit([sidebar, divider, transcript]), divider, input_box, status_bar])`；`ConditionalContainer` 让 `Ctrl+B` toggle sidebar；keybindings：`Esc Enter` 提交、`Tab` 切焦点、`Ctrl+B/N/D/L/Q/C`、sidebar focused 时 `↑↓` 移动 + `Enter` 切会话。
    - `ui/commands.py`：`CommandRegistry` + `register_default_commands()`；14 个命令（`/help /quit /exit /clear /model /rag /think /register /login /logout /whoami /sessions /new /switch /title /delete`）；handler 签名 `async (ctx: CommandContext, args: list[str]) -> None`；`CommandContext.services: object`（loose-typed）让 commands 模块不 import core/app/db，依赖通过 `getattr(services, "do_xxx", None)` 取 callback。
  - **`app/chat_app.py` 重写**（最大改动）：
    - 旧 `run_chat` 改名 `run_legacy_chat`，逻辑不动，留给 `--legacy` flag + `tests/integration/test_cli_boot.py`。
    - 新 `run_tui_chat`：构建 TuiState/TranscriptBuffer → ping ollama + `list_models()` → 按 token 决定 file/db memory → 构建 `ChatServiceProvider`（带 `set_model/set_session/reset_session`）→ 注册 11 个 service callbacks（`do_register / do_login / do_logout / do_new_session / do_switch_session / do_set_current_title / do_delete_current / do_refresh_sessions / set_provider_model`）→ build Application → `await app.run_async()`。
    - **没起 ollama / 没登录都能跑**：ollama unreachable → provider=None + transcript 红字提示，但 TUI 还能看 sidebar/输 commands；DB 挂 → `memory_mode = "file (db-unavailable)"`。
    - `_on_send` 把 stream events 翻译成 transcript 操作：`token → append_to_assistant`、`done → end_assistant(duration_ms=...)`、`retrieval → add_system("retrieved N chunk(s)")`、`error → add_error(code, msg)`；每轮结束后 `_refresh_sessions()` 让 sidebar 显示最新 message_count + 新建的 session row。
    - `ChatServiceProvider` 加 `set_model / set_session / reset_session / session_id property`，`reply()` 透传 `model=self._model` 到 `service.generate()`。
  - **`app/cli.py`**：`chat` 子命令加 `--legacy` flag；默认 `run_tui_chat()`；`--legacy` 走 `run_legacy_chat()`。
  - **测试（轻量，按用户指示不过度规范）**：
    - `tests/unit/ui/test_transcript_buffer.py` 4 条：add_user/system + streaming 累积 + 中途 add_error 自动 flush + cap 1000 drop oldest。
    - `tests/unit/ui/test_sessions_pane_render.py` 2 条：empty placeholder + cursor/current 高亮（断言 reverse style 出现在 cursor 行的 tuples）。
    - `tests/unit/core/test_session_meta.py` 1 条：FileChatMemory 现算 title 含中文 24 字截断。
    - **不做** TUI 集成测（全屏 Application 没法 subprocess 断言 stdout）；现有 `test_cli_boot.py::test_main_help_exits_zero` + 旧 legacy 的 `--legacy` flag 路径覆盖启动健壮性。
  - **偏离 design.md §11 (`/register` 不自动登录)**：保留——故意分两步，避免新手"为什么注册了 memory 还是 file"。
  - **偏离 tasks.md §8.4** (`test_chat_legacy_mode_quits`)：现有 `test_main_help_exits_zero` 已覆盖入口路径；非 tty 环境 `--legacy` 仍会试图启 prompt_toolkit 的 `prompt_async`，需要 mock，**性价比低，跳过**。
  - **bcrypt 兼容 shim** 是本 change 的副产物：`/login` 不再吐 `(trapped) error reading bcrypt version` traceback，UX 巨幅改善。
  - **依赖**：零新增（`prompt_toolkit>=3.0.43` v0.5 已加）。
  - **质量门**：`ruff check .` All passed；`ruff format --check .` 111 files；`mypy --strict . --explicit-package-bases` → **Success: no issues found in 113 source files**；`uv run pytest -q` → **128 passed**（121 + 7 新增 = 4 transcript + 2 sessions render + 1 session_meta）；`make ci` 全绿。
  - **冒烟**：`python main.py chat --help` 显示 `--legacy`；`echo "/quit" | python main.py chat --legacy` 旧 banner 正常退出；TUI 模式（`python main.py chat` 在真 tty）显示三栏布局，`Ctrl+B` 折叠 sidebar，`Esc Enter` 发送，`Ctrl+Q` 退出。`/model` 列出本机模型；`/model <name>` 运行时切换；`/register` 走完三步进 DB。




