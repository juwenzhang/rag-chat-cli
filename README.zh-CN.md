# rag-chat-cli

[![ci](https://github.com/juwenzhang/rag-chat-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/juwenzhang/rag-chat-cli/actions/workflows/ci.yml)

> 📖 **Language / 语言**：**简体中文** · [English](README.md)

一款跑在终端里的 ReAct Agent —— 后端可选本地 Ollama 或任意
OpenAI 兼容 endpoint（vLLM / Together / Groq / LM Studio …），自带
基于 Postgres + pgvector 的混合检索 RAG、MCP 工具集成、用户级长期
记忆，以及一个把同一份事件流通过 SSE / WebSocket 暴露出去的
FastAPI 接口层 —— 想接前端／IDE 插件／别的客户端，直接吃这个流。

整体架构蓝图见 [AGENTS.md](AGENTS.md)；流式事件协议见
[docs/STREAM_PROTOCOL.md](docs/STREAM_PROTOCOL.md)。

## 关键能力

- **ReAct 循环** —— 多步工具调用，事件流里同时有 `thought` /
  `tool_call` / `tool_result`，受 `ResourceLimits` 约束（`max_steps` /
  单步工具数上限 / 单次调用超时）。
- **双后端，单协议** —— `OllamaClient`（本地）和 `OpenAIClient`
  （OpenAI / vLLM / Together / Groq / 任何兼容服务）实现同一个
  `LLMClient` Protocol，切换 provider 不动 Agent 代码。
- **MCP 集成** —— stdio JSON-RPC client + `McpTool` 适配器，任意
  [Model Context Protocol](https://modelcontextprotocol.io) server
  对 Agent 来说就是普通工具。
- **混合检索 RAG** —— `PgvectorKnowledgeBase` 把向量检索（pgvector）
  和 `pg_trgm` 词法分用 RRF 融合，留出 `Reranker` hook；引用以
  `[N]` 标注回填到回答里，CLI / API 都能看到。
- **双模式知识库管理** —— `/save` 和 `/reflect`（critic 判分的自动
  入库）同时支持磁盘版 `FileKnowledgeBase`（未登录，存在
  `~/.config/rag-chat/kb/`）和 Postgres 的 `PgvectorKnowledgeBase`
  （登录态）。`/kb sync` 一键把本地积累迁移到 pgvector。
- **持久化记忆** —— 单会话历史（文件或 Postgres）、用户级长期记忆
  + `FactExtractor` 抽取钩子、context-window-aware 的历史摘要压缩。
- **统一流式协议** —— 同一份 `Event` 在 CLI 里渲染，从
  `POST /chat/stream`（SSE）和 `/ws/chat`（WebSocket，支持 abort）
  原样发出。
- **后台 Worker** —— Redis 后端的 FIFO 队列 + Worker pump，把
  ingestion / reindex 等重活从请求链路上挪走。
- **可观测性** —— 可选 OpenTelemetry tracer（没装 OTel 自动降级为
  no-op）+ `UsageAccumulator` 把不同 provider 的 token / 成本数据
  normalize 到同一份口径。

## 架构

```
main.py
└─ app/cli.py            {chat, serve, ingest, worker, train}
   └─ app/chat_app.py    REPL + factory wiring
      └─ core/chat_service.py        ReAct 循环（所有可调节点都挂在这里）
         ├─ core/llm/                {OllamaClient, OpenAIClient} : LLMClient
         ├─ core/tools/              ToolRegistry + FunctionTool + (MCP) McpTool
         ├─ core/knowledge/          PgvectorKnowledgeBase + Reranker + Ingestor
         ├─ core/memory/             {File,Db}ChatMemory + UserMemoryStore
         ├─ core/tokens.py           Tokenizer + TokenBudget
         ├─ core/history.py          HistorySummarizer
         ├─ core/prompts.py          PromptBuilder
         ├─ core/limits.py           ResourceLimits
         ├─ core/observability.py    Tracer + UsageAccumulator
         ├─ core/mcp/                stdio JSON-RPC client + adapter
         ├─ core/workers/            Redis queue + worker
         └─ core/streaming/          Event vocabulary + AbortContext

api/  → 与 CLI 共享 ChatService.generate()，外面套 SSE / WS 帧 + auth deps
```

每个模块都有 Protocol。后面想加 Anthropic LLMClient、Cohere reranker、
Postgres-backed queue、HTTP MCP transport —— 都是单文件改动，
`ChatService` 一行不用动。

## 环境要求

- Python ≥ 3.10
- [uv](https://github.com/astral-sh/uv) 管理依赖
- 本地跑着的 Ollama（或一份 `OPENAI_API_KEY`，对接 OpenAI 兼容
  endpoint）
- Docker（启动 Postgres + pgvector + Redis，靠 `docker-compose.yml`）

## Day 0 —— 从 clone 到第一条回复

这是「我刚 clone 完仓库，5 分钟跑起来」的标准流程。所有命令都
能直接复制粘贴。

```bash
# 1. 安装 Python 依赖
uv sync --all-extras

# 2. 确认 Ollama 在跑，拉 CLI 用到的两个模型：
#    - 聊天模型（默认 qwen2.5:1.5b，可以改）
#    - 嵌入模型（/save / /reflect / /kb search / RAG 检索都需要）
ollama serve &                       # 没跑的话开个新终端起来
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text         # ⚠️ 必须拉，否则 /save 会报 404

# 3. 配环境变量
cp .env.example .env
# 编辑 .env：把 DATABASE_URL 的 @postgres 改成 @localhost
#   DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5432/ragdb
# 生成强 JWT 密钥（替换 placeholder）：
openssl rand -hex 32                 # 拷到 .env 的 JWT_SECRET=...

# 4. 起 Postgres + 跑迁移（幂等，重复跑无副作用）
make db.up                           # docker compose up postgres + pgvector
make db.init                         # 连通性 probe + alembic upgrade head + pgvector 校验

# 5. 启动 REPL
make dev.cli                         # = uv run python -m main chat
```

正常的话你会看到 model banner 和提示符。输入 `/` 会立刻弹出斜杠
命令自动补全菜单；输入问题开始聊。

> 跳了第 2 步，`/save` 报 "model 'nomic-embed-text' not found"？
> 直接 `ollama pull nomic-embed-text` 然后重试 —— 不用重启 REPL。

> 跳了第 4 步、只想用纯本地文件 KB？也可以 —— CLI 不依赖数据库就
> 能跑，本地知识库存在 `~/.config/rag-chat/kb/`。只是 `/login` 和
> 基于 Postgres 的 RAG 检索用不上。

## REPL 常用快捷

REPL 内：

- 输入 `/`，**命令自动补全菜单**立刻弹出 —— 方向键或 `Tab` 选中
  命令，右侧带描述。
- 输入 `/help` 渲染完整的命令面板（分组 + 框）。
- `Enter` 发送；`Ctrl+J` 换行；`↑`/`↓` 调历史（持久化在
  `~/.config/rag-chat/history`）；`Ctrl+L` 清屏。

### 斜杠命令

| 分组 | 命令 | 作用 |
|---|---|---|
| **session** | `/sessions [id\|idx]` | 列出已保存会话（带参就当 `/switch` 用） |
| | `/switch [id\|idx]` | 选会话（不带参 = 列表 + 提示） |
| | `/new [title]` | 开新会话 |
| | `/title <text>` | 改当前会话标题 |
| | `/delete` | 删当前会话 |
| **model** | `/model` | 列出已拉取的 Ollama 模型 |
| | `/model <name>` | 运行时切换模型（不用重启） |
| | `/model pull <name>` | 从 registry 拉新模型 |
| **runtime** | `/rag [on\|off]` | 开关检索增强 |
| | `/think [on\|off]` | 开关「深度思考」提示（仅 UI 标记） |
| **knowledge** | `/kb` | 知识库摘要（数量 + 最近 doc + 当前后端） |
| | `/kb list` | 列出当前 KB 里的文档 |
| | `/kb show <idx\|id>` | 看某文档的元数据 + 前几个 chunk |
| | `/kb search <query>` | 预览检索（不走 LLM，纯打分） |
| | `/kb delete <idx\|id>` | 删文档及其 chunks（带二次确认） |
| | `/kb sync` | 本地 KB → pgvector（仅登录态） |
| | `/save [title]` | 把最近一轮 Q+A 存进当前 KB |
| | `/reflect [on\|off\|<0..1>]` | 自动保存高质量回答（带阈值） |
| **auth** | `/register` | 注册账号 |
| | `/login` | 登录（token 存到 `~/.config/rag-chat/token.json`，权限 0600） |
| | `/logout` | 吊销 refresh token + 清除本地 token |
| | `/whoami` | 打印当前 user id |
| | `/ollama-auth [key\|clear\|show]` | 设置 / 清除托管 Ollama 的 Bearer key |
| **misc** | `/clear` | 清屏 |
| | `/help` | 打开命令面板 |
| | `/quit`（`/exit`） | 退出 REPL |

### 知识库管理

`/kb` 系列命令操作的是**当前活跃**的 KB —— 哪个生效取决于登录态：

- **未登录** → `FileKnowledgeBase`，路径 `~/.config/rag-chat/kb/`（JSONL
  on disk + stdlib 余弦检索）。除了 embed model 不依赖外部组件，全部操作
  留在本机。
- **已登录**（`/login`）→ `PgvectorKnowledgeBase`，落 Postgres。同一套
  admin API（`list` / `show` / `search` / `delete` + `/save` 走的
  `add_document`），底层是 `vector(768)` 列 + ivfflat 索引。文档按
  `user_id` 隔离。

典型使用流程：

```
# 手动保存 —— 显式一对 Q+A
> 问一个有用的问题
> /save
saved → local · 1a2b3c4d · ... · /kb show 1a2b3c4d

# 自动保存 —— critic LLM 判每轮回答，达到置信度阈值才存
> /reflect on
> /reflect 0.7                # 阈值（0-1），越高越严
> 后面问问题就行，符合条件的会在背景里自动入库

# 迁移：未登录积累的本地 KB → 登录后回流到 pgvector
> /login
> /kb sync                    # 把本地文档重新 embed 写进 PG
```

`/reflect` 写入的是 critic 蒸馏出的 "fact card"（带原始 Q+A 一起），
打 `auto-saved` 标签，便于 `/kb list` 一眼区分。默认 **off**，需要显
式开启。

## 快速开始 —— API

假设你已经走完了 [Day 0](#day-0--从-clone-到第一条回复) —— Postgres
起着、迁移到 head、`.env` 里有真实的 `JWT_SECRET`。然后：

```bash
make dev.api              # = uvicorn api.app:create_app，reload 模式
# 或者：
make dev.api PORT=8001    # 8000 被占用时
```

> SQLite（`DATABASE_URL=sqlite+aiosqlite:///./.dev.db`）仍然给测试
> 套件和零安装的路由 smoke test 用，但**不推荐**作为开发默认值：
> Pgvector retriever 用了 `Vector` 列和 `pg_trgm` operator，SQLite
> 上没有实现，`/chat/stream` 走 RAG 会在查询时挂掉。

冒烟：

```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"password1demo"}'
# 201 + {"id":"…","email":"me@example.com",…}
```

### REST / SSE / WebSocket 速查

| Method | Path | Auth | 备注 |
|---|---|---|---|
| `GET` | `/health` | public | liveness |
| `POST` | `/auth/register` | public | |
| `POST` | `/auth/login` | public | 返回 access + refresh |
| `POST` | `/auth/refresh` | refresh token | 开启 rotation |
| `POST` | `/auth/logout` | refresh token | |
| `GET` `PATCH` | `/me` | bearer | |
| `POST` `GET` | `/chat/sessions` | bearer | |
| `GET` | `/chat/sessions/{id}/messages` | bearer | |
| `POST` | `/chat/messages` | bearer | 非流式（内部聚合 SSE） |
| `POST` | `/chat/stream` | bearer | **SSE** —— 事件：`retrieval` / `token` / `thought` / `tool_call` / `tool_result` / `done` / `error` |
| `WS` | `/ws/chat` | bearer（`bearer,<jwt>` subprotocol 或 `?token=<jwt>`） | 支持 `{"type":"abort"}` |
| `POST` `GET` | `/knowledge/documents` | bearer | |
| `POST` | `/knowledge/documents:reindex` | bearer | 入队到 worker（返回 202） |
| `GET` | `/knowledge/search` | bearer | |

完整事件词表 + 顺序约定见
[docs/STREAM_PROTOCOL.md](docs/STREAM_PROTOCOL.md)。

`make openapi` 重新生成 [docs/openapi.json](docs/openapi.json)；
`make test.api` 用 `httpx.ASGITransport` 跑内存版 SQLite 上的路由测试。

## 入库 + 后台 Worker

```bash
# 同步入库（CLI 阻塞到完成）
uv run python -m main ingest path/to/dir --recursive --title "我的文档"

# 入队，立即返回
uv run python -m main ingest path/to/dir --recursive --async

# 跑 Worker（另一个终端）
uv run python -m main worker
# → [worker] ingested /x/a.md → doc=… chunks=12
```

Job 协议 / 队列语义 / 重试预期都在
[`core/workers/queue.py`](core/workers/queue.py)。

## 配置

所有可调项都在 [settings.py](settings.py)（pydantic-settings）声明，
`.env` 覆盖。变量按用途分组，**同时支持扁平名**（`JWT_SECRET`）
和**嵌套名**（`AUTH__JWT_SECRET`），冲突时嵌套优先。

| 分组 | 扁平 env 名 | 作用 |
|---|---|---|
| `app` | `APP_ENV`, `APP_HOST`, `APP_PORT`, `LOG_LEVEL` | 运行时 |
| `auth` | `JWT_SECRET`, `JWT_ALG`, `ACCESS_TTL_MIN`, `REFRESH_TTL_DAYS` | 鉴权 |
| `db` | `DATABASE_URL`, `DB_POOL_SIZE`, `ECHO_SQL` | 持久化 |
| `redis` | `REDIS_URL` | worker 队列 + 缓存 |
| `ollama` | `OLLAMA_BASE_URL`, `OLLAMA_CHAT_MODEL`, `OLLAMA_EMBED_MODEL`, `OLLAMA_API_KEY` | 本地 / 托管 Ollama |
| `openai` | `OPENAI_BASE_URL`, `OPENAI_CHAT_MODEL`, `OPENAI_EMBED_MODEL`, `OPENAI_API_KEY`, `OPENAI_ORGANIZATION` | OpenAI 兼容 endpoint |
| `retrieval` | `RETRIEVAL_ENABLED`, `RETRIEVAL_TOP_K`, `RETRIEVAL_MIN_SCORE`, `RETRIEVAL_EMBED_DIM` | RAG 默认值 |
| `rate_limit` | `RATE_LIMIT_PER_MIN` | API 限流 |

`APP_ENV=prod` 模式下，若 `JWT_SECRET` 还是 placeholder 启动会失败。
`openssl rand -hex 32` 出来的就能直接用。

## 数据库与迁移

数据库对 **CLI 不是必需**的 —— Postgres 不通时聊天会自动落到文件
记忆。想跑完整 schema：

```bash
make db.up          # 通过 docker compose 起 postgres + pgvector
make db.init        # probe + alembic upgrade head + pgvector 校验
make db.shell       # psql 交互
```

迁移历史：

- `0001_init` —— users / chat_sessions / messages / documents / chunks / refresh_tokens
- `0002_add_tool_message_fields` —— `messages.tool_call_id` + `messages.tool_calls`（Postgres 上是 JSONB），支撑 tool-role 消息
- `0003_add_user_memories` —— `user_memories` 表，存用户级长期事实

单元测试默认走内存版 SQLite（不依赖 docker）。需要真实 pgvector 的
集成测试用 `pytest -m pg` 触发。

## 开发

```bash
make ci             # ruff check + format check + mypy strict + pytest
make lint           # ruff check
make fmt            # ruff format（写盘）
make typecheck      # mypy --strict，覆盖 app/ core/ ui/ api/ db/
make test           # 所有测试
make test-fast      # 跳过 slow / pg / redis / integration 标记
make test-cov       # pytest-cov（软门）
make test-cov-strict   # 强制 AGENTS.md §12 覆盖率阈值
make openapi        # 重新生成 docs/openapi.json
make openapi.check  # 对比当前代码与 docs/openapi.json（CI 用）
```

pre-commit hooks：`pre-commit install` 一次，之后 commit 时自动跑
ruff + format。

## 项目结构

```
├── AGENTS.md                  # 架构蓝图（single source of truth）
├── docs/
│   ├── STREAM_PROTOCOL.md     # 流式事件词表
│   └── openapi.json           # 生成产物；CI 会做 drift 检查
├── settings.py                # pydantic-settings 单入口
├── .env.example               # env 模板
├── main.py                    # CLI 薄壳 → app.cli.main
├── app/                       # 编排层（唯一同时依赖 ui/ 与 core/ 的层）
│   ├── cli.py                 #   argparse: chat / serve / ingest / worker / train
│   ├── chat_app.py            #   REPL + ChatService factory
│   └── auth_local.py          #   ~/.config/rag-chat/token.json
├── ui/                        # 展示层（rich + prompt_toolkit）
│   ├── theme.py · console.py · markdown.py
│   ├── chat_view.py           #   流式渲染器 + help 面板
│   └── prompt.py              #   PromptSession + SlashCompleter + Dispatcher
├── core/                      # 领域层（provider-agnostic，无 I/O imports）
│   ├── chat_service.py        #   ReAct 循环 —— 唯一集成点
│   ├── llm/                   #   LLMClient protocol + Ollama + OpenAI 实装
│   ├── tools/                 #   Tool protocol + ToolRegistry + FunctionTool
│   ├── knowledge/             #   PgvectorKnowledgeBase + Ingestor + Reranker hook
│   ├── memory/                #   ChatMemory（File/DB）+ UserMemoryStore + FactExtractor
│   ├── mcp/                   #   MCP stdio client + Tool 适配器
│   ├── workers/               #   RedisJobQueue + Worker pump
│   ├── streaming/             #   Event TypedDict + AbortContext
│   ├── tokens.py · history.py · prompts.py · limits.py · observability.py
│   └── auth/                  #   bcrypt + JWT + refresh rotation
├── db/                        # SQLAlchemy 2.x async + models
├── alembic/versions/          # 0001 / 0002 / 0003
├── api/                       # FastAPI app（routers / deps / middleware）
├── scripts/                   # 一次性运维（db_init, check_coverage 等）
├── tests/                     # pytest（unit + integration + api）
├── openspec/                  # spec 提案 + 归档
├── Makefile · docker-compose.yml · pyproject.toml
└── README.md / README.zh-CN.md
```

分层规则（AGENTS.md §3）：`ui/` 永不 import `core/` / `db/` / `api/`；
`core/` 永不 import `db/` / `api/` / `ui/`；`app/` 是唯一能把它们
串起来的层。

## 贡献

- 新提案 → `openspec/changes/<kebab-name>/`（`proposal.md` +
  `design.md` + `tasks.md`）。
- 已完成的 change → 归档到
  `openspec/changes/archive/YYYY-MM-DD-<name>/`。
- 稳定能力规范 → `openspec/specs/<capability>/spec.md`。

提 PR 前请本地跑一次 `make ci`，四个质量门（ruff / format / mypy /
pytest）必须全绿。

## 许可证

MIT
