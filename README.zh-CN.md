# rag-chat-cli

[![ci](https://github.com/juwenzhang/rag-chat-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/juwenzhang/rag-chat-cli/actions/workflows/ci.yml)

> 📖 **Language / 语言**：**简体中文** · [English](README.md)

基于 Ollama、Postgres + pgvector、Redis 与 FastAPI 构建的 RAG 聊天平台（CLI + Web）。
整体架构与路线图参见 [AGENTS.md](AGENTS.md)；具体的施工计划位于 [openspec/changes/](openspec/changes/)。

## 路线图（顶层 change 队列）

- **P0** `bootstrap-settings-and-env` ✓ 已归档 — 单一配置入口（`settings.py` + `.env`）
- **P1** `restructure-cli-ui-opencode-style` ✓ 已归档 — 最小 CLI 骨架（`ui/` + `app/`）
- **P2** `split-core-domain-layer` ✓ 已归档 — `core/` 领域包（Ollama + ChatService）
- **P3** `setup-quality-gates-ci-cd` ✓ 已归档 — ruff / mypy / pytest-cov / pre-commit / GitHub Actions
- **P4** `setup-db-postgres-pgvector-alembic` ✓ 已归档 — 数据库 schema + 异步 SQLAlchemy + Alembic
- **P5** `add-redis-and-workers` — 任务队列与后台 worker
- **P6** `add-fastapi-rest-api` + `add-jwt-auth` — HTTP 暴露层
- **P6** `add-sse-and-websocket-streaming` — 流式响应
- **P7** `implement-rag-retrieval-pgvector` — 检索管线
- **P8** `bootstrap-web-vite-react-ts` + `build-web-views-auth-chat-knowledge` — Web 前端
- **P9** `add-observability-otel` + `containerize-with-docker-compose` — 可观测性与容器化

实时状态请运行 `openspec list` 查看。

## 环境要求

- Python >= 3.10
- [uv](https://github.com/astral-sh/uv) 用于依赖管理
- 本地运行的 Ollama（开发期）
- 带 pgvector 的 Postgres 与 Redis（随 `docker-compose.yml` 提供，P4/P5 落地后逐步启用）

## 安装

```bash
# 仅核心运行依赖
uv sync

# 核心 + 开发工具（pytest、ruff、mypy、pre-commit 等）—— 贡献者推荐
uv sync --all-extras
```

## 首次运行

复制示例环境变量文件并按需修改：

```bash
cp .env.example .env
```

所有环境变量都在 `settings.py`（pydantic-settings）中声明；完整字段列表见
[AGENTS.md](AGENTS.md) §7。

## 配置

所有配置统一通过 [settings.py](settings.py)（pydantic-settings）读取，`.env`
仅作为覆盖项。完整字段列表见 [AGENTS.md](AGENTS.md) §7。

环境变量按用途分组（app / auth / db / redis / ollama / retrieval / rate_limit），
**同时支持扁平名**（`JWT_SECRET`）与**嵌套名**（`AUTH__JWT_SECRET`），两者冲突时
嵌套形式优先。

## 数据库（Postgres + pgvector）

数据库层对 **CLI 运行不是必需**的 —— 当 Postgres 不可达时，聊天循环会回退到基于
文件的会话记忆。当你需要完整 schema（P4+）时再启动数据库：

```bash
# 1. 通过 docker compose 启动 postgres（pgvector/pgvector:pg16）
make db.up

# 2. 初始化：连通性探测 + alembic upgrade head + 校验 pgvector extension
make db.init
# → [db-init] connectivity: OK
#   [db-init] migrations: at head
#   [db-init] pgvector: installed

# 可选：进入容器里的 psql 交互 shell
make db.shell
```

单元测试**默认使用 SQLite in-memory**（不需要 docker）：`make test`。
依赖真实 pgvector 的集成测试用 `@pytest.mark.pg` 标记，起好 `make db.up` 后可通过
`pytest -m pg` 触发。

## 使用方式

CLI 入口是 [main.py](main.py)，它只是一个薄转发层，实际逻辑在
[app/cli.py](app/cli.py)。

```bash
# 查看所有子命令
uv run python main.py --help

# 交互式聊天（默认子命令）
uv run python main.py chat
uv run python main.py          # 等价写法

# 以下为暂未实现的占位子命令（返回 exit code 2）
uv run python main.py serve    # FastAPI 服务（P6 实装）
uv run python main.py train    # LoRA 训练
uv run python main.py ingest   # 知识库入库
```

### 聊天键位（AGENTS.md §11）

| 按键 | 动作 |
|---|---|
| `Esc` + `Enter` | 发送多行消息 |
| `F2` | 发送（替代键） |
| `↑` / `↓` | 历史（持久化在 `~/.config/rag-chat/history`） |
| `Ctrl-L` | 清屏 |
| `Ctrl-D` / `/quit` / `/exit` | 退出 |
| `/help` | 列出所有斜杠命令 |
| `/clear` | 清屏 |
| `/new` | 开启新的本地会话（清空当前对话记忆） |
| `/model` `/retrieve` `/login` `/logout` | 预留（输出 "not implemented yet"） |

> P1 的默认回复源是进程内的 `EchoReplyProvider` —— 把输入原样以流式 token 回显，
> 方便在没有 Ollama 的情况下验证整个渲染管线。真正的 LLM 流式响应由 P2
> `split-core-domain-layer` 接入（已归档）。

### 质量门

```bash
make ci            # 一键跑完：ruff check + format check + mypy strict + pytest
make test          # 仅 pytest
make test-cov      # pytest + 覆盖率（软门，报告不退出码）
make test-cov-strict  # 覆盖率达不到 AGENTS.md §12 阈值则失败
make lint          # ruff check
make fmt           # ruff format
make typecheck     # mypy --strict
```

更多开发流程细节见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

## 项目结构

```
├── AGENTS.md                # 架构蓝图（single source of truth）
├── settings.py              # 单一配置入口（pydantic-settings）
├── .env.example             # 环境变量模板
├── main.py                  # CLI 薄壳 → app.cli.main
├── app/                     # 编排层（唯一同时依赖 ui/ 与 core/ 的层）
│   ├── cli.py               #   argparse 入口（chat / serve / train / ingest）
│   └── chat_app.py          #   run_chat 循环 + ReplyProvider Protocol
├── ui/                      # 展示层（rich + prompt_toolkit）
│   ├── theme.py             #   冻结的配色方案
│   ├── console.py           #   Console 工厂、banner、分隔线
│   ├── markdown.py          #   增量 Markdown 渲染
│   ├── chat_view.py         #   Event TypedDict + ChatView
│   └── prompt.py            #   PromptSession + SlashDispatcher
├── core/                    # 领域层（无 I/O 副作用，provider-agnostic）
│   ├── llm/                 #   LLMClient Protocol + Ollama 实装
│   ├── memory/              #   ChatMemory（File 实现）
│   ├── knowledge/           #   KnowledgeBase Protocol + 占位实现
│   └── chat_service.py      #   唯一的 app/ ↔ core/ 握手点
├── db/                      # 数据层（P4）
│   ├── base.py              #   DeclarativeBase + 命名约定
│   ├── session.py           #   异步 engine / sessionmaker / get_session
│   └── models/              #   users / chat_sessions / messages / documents / chunks / refresh_tokens
├── alembic/                 # 数据库迁移（P4）
│   ├── env.py               #   async + sync 双模 env
│   └── versions/0001_init.py
├── scripts/                 # 运维脚本
│   ├── db_init.py           #   一键 probe + migrate + 校验 pgvector
│   └── check_coverage.py    #   分层覆盖率门（stdlib-only）
├── tests/                   # pytest（单元 + 集成）
├── docs/                    # 开发者文档（DEVELOPMENT.md 等）
├── openspec/                # 规范与 change 提案（施工图）
├── Makefile                 # 日常命令集合（make help 列全）
├── docker-compose.yml       # 服务栈（postgres + ollama，P5+ 后补 redis / api）
├── pyproject.toml           # Python 依赖（uv 管理）
├── .pre-commit-config.yaml  # pre-commit 钩子
├── .github/workflows/ci.yml # GitHub Actions（lint / typecheck / test matrix）
└── README.md / README.zh-CN.md
```

分层规则见 AGENTS.md §3 / §3.1 —— `ui/` 永远不 import `core/` / `db/` / `api/`。

## 贡献

- 新提案 / 设计 → `openspec/changes/<kebab-name>/`（proposal.md + design.md + tasks.md）
- 已完成的 change → 通过 `opsx/archive` 或 openspec CLI 归档到
  `openspec/changes/archive/YYYY-MM-DD-<name>/`
- 能力规范（稳定契约）→ `openspec/specs/<capability>/spec.md`
- 全局规则 / 变更日志 → `AGENTS.md`（§19 是变更日志）

PR 前请本地跑一次 `make ci`，确保四个质量门（ruff / format / mypy / pytest）
全绿。

## 许可证

MIT
