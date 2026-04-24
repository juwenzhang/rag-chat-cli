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
