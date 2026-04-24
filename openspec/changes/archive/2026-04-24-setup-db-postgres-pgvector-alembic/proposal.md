# Proposal: Setup PostgreSQL + pgvector + SQLAlchemy async + Alembic

## Why

AGENTS.md §4 明确要求：

> DB：PostgreSQL 15+，扩展：`pgvector`（RAG 向量列）、`pg_trgm`（模糊匹配，可选）。
> ORM：`SQLAlchemy 2.x async` + `asyncpg`。
> 迁移：`Alembic`，在 `alembic/` 目录管理。

当前项目**完全没有数据库层**：会话保存在 `conversations/*.json`，知识保存在 `knowledge/*.md/json`。这带来：
- 无法多实例共享状态（阻塞 Web 化）。
- 无法做向量检索（RAG 召回精度差）。
- 无法接入 JWT 用户体系（Change 5 强依赖 `User` 表）。

本次是**后端 Web 化的地基**（AGENTS.md §15 P4 的核心），必须在 JWT / FastAPI / RAG 之前完成。

## What Changes

- 新增 `db/` 目录（§2 约束）：
  - `db/base.py` — `DeclarativeBase` 基类、命名约定。
  - `db/session.py` — async engine、sessionmaker、`get_session()` 依赖注入 helper。
  - `db/models/` — ORM 模型目录，按表拆文件：`user.py`、`session.py`（会话）、`message.py`、`document.py`、`chunk.py`、`token.py`（API key / refresh token）。
- 新增 `alembic/` 目录 + `alembic.ini`：
  - `env.py` 配置 async driver + 目标 metadata。
  - 初始 migration `0001_init.py`：建所有表 + `CREATE EXTENSION IF NOT EXISTS vector;`。
  - `chunks` 表的 `embedding` 列用 `Vector(768)`（对齐 `nomic-embed-text` 默认维度，可配置）。
  - 建立 ivfflat 索引（`lists=100`）for `chunks.embedding`。
- 新增 `settings.db` 字段（若 Change 1 已含则复用）：`database_url`、`pool_size`、`pool_recycle`、`echo_sql`。
- 新增 `docker-compose.yml` 的 `postgres` 服务（profile=`db`），镜像 `pgvector/pgvector:pg16`。
- 提供一次性初始化脚本 `scripts/db_init.py`：检查连通 + 执行 `alembic upgrade head`。
- `core/memory/chat_memory.py` **新增** `DBChatMemory` 实现（与原 `FileChatMemory` 并列，通过 settings 选择），但**本次默认仍为 File**；DB 实现仅提供 + 单测，不切主路径，避免 Big Bang。

## Non-goals

- 不实现向量检索业务逻辑（仅建表 + 索引，Change 9 再接召回）。
- 不接 FastAPI 的 `Depends(get_session)`（Change 6 做）。
- 不迁移现有 `conversations/*.json` 历史数据（后续 Change 单独做数据迁移脚本）。
- 不建 `users` 的 password 字段约束（Change 5 做）。

## Impact

- **新增目录**：`db/`、`db/models/`、`alembic/`、`alembic/versions/`。
- **新增文件**：`alembic.ini`、`db/base.py`、`db/session.py`、`db/models/*.py`（约 6 个）、`scripts/db_init.py`。
- **修改**：`pyproject.toml`（新增依赖）、`docker-compose.yml`（新增 postgres service）、`.env.example`（补 `DB__DATABASE_URL`）。
- **依赖新增**：`sqlalchemy[asyncio]>=2.0`、`asyncpg>=0.29`、`alembic>=1.13`、`pgvector>=0.2.5`。
- **风险**：中。初次引入 DB，本地需要 docker；提供 `SQLITE_FALLBACK` 仅用于 CI 单测（不支持 pgvector，测试用 `sqlalchemy.JSON` 字段 stub）。
- **回退方式**：`alembic downgrade base` + 删除 `db/` `alembic/` + compose 移除 postgres。
