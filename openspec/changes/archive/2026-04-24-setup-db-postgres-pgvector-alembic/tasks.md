# Tasks: PostgreSQL + pgvector + SQLAlchemy async + Alembic

> v0.8 note — 落地裁剪策略与 AGENTS.md §19 v0.8 条目对应。规则：
>   * **[x]** 有效且已完成
>   * **[x] (N/A - future change supersedes)** 原假设的文件/模块尚未诞生，本 change 无对象可操作
>   * **[x] (adjusted)** 目标有效但实现路径与 design 略有差异（原因见 AGENTS.md §19 v0.8）
>   * **[x] (deferred)** 超出本 change 的职责边界，推迟到后续 change

## 1. 依赖

- [x] 1.1 `pyproject.toml` 新增 `sqlalchemy[asyncio]>=2.0.29` / `asyncpg>=0.29` / `alembic>=1.13` / `pgvector>=0.2.5` / `greenlet>=3.0`。
- [x] (adjusted) 1.2 dev 组新增 `aiosqlite>=0.20`；`pytest-asyncio` 已在 P3 就绪，未新增；`pytest-postgresql` **未引入**（本 change 的 `@pytest.mark.pg` 留给 P5 结合真正的 service fixture 实装）。
- [x] 1.3 `uv sync --extra dev` 成功，venv 内新增 9 个包（sqlalchemy/aiosqlite/alembic/asyncpg/pgvector/greenlet/mako/markupsafe/async-timeout）。

## 2. Settings 扩展

- [x] 2.1 `DBSettings.database_url` 已存在；补 `pool_size / pool_recycle / echo_sql`。
- [x] 2.2 `.env.example` 补 `DATABASE_URL`（已有）+ 新三个 pool 注释项。
- [x] 2.3 `RetrievalSettings.embed_dim: int = 768` 已补；扁平别名 `RAG_EMBED_DIM` 同步入 `_FLAT_TO_NESTED`。

## 3. `db/base.py`

- [x] 3.1 `db/__init__.py` 已建，`__all__ = []`。
- [x] 3.2 `class Base(DeclarativeBase)` + `NAMING_CONVENTION` 完成。
- [x] 3.3 `from db.base import Base` 干净 import（`uv run python -c "from db.base import Base"` 无副作用）。

## 4. `db/session.py`

- [x] 4.1 `init_engine(url=None, *, echo=None) -> AsyncEngine`（echo 默认读 settings，SQLite 不传 pool_size）。
- [x] 4.2 `async def get_session() -> AsyncIterator[AsyncSession]`。
- [x] 4.3 `async def dispose_engine() -> None`（幂等）。
- [x] 4.4 默认从 `settings.db.database_url` 取值 —— 通过懒 import 避免模块级副作用。
- [x] 4.5 单测 `tests/unit/db/test_session.py`：init / cache / `get_session` / `dispose_engine` 共 4 条全部通过。

## 5. Mixins

- [x] (adjusted) 5.1 新建 `db/models/_mixins.py`：`UUIDMixin` 的 UUID 类型是 **`TypeDecorator`**（不是 `PGUUID.with_variant`），否则 SQLite 下 bind UUID 实例会 `InterfaceError`。`TimestampMixin` 用 `server_default=func.now()` + `onupdate=func.now()`。
- [x] (adjusted) 5.2 上述 `_UUID` TypeDecorator 在 `load_dialect_impl` 里根据 dialect.name 切换 `PGUUID(as_uuid=True)` / `String(36)`；`process_bind_param` / `process_result_value` 双向转换。

## 6. 模型文件

- [x] 6.1 `db/models/user.py` `User` ✓
- [x] 6.2 `db/models/session.py` `ChatSession` (表名 `chat_sessions`) ✓
- [x] 6.3 `db/models/message.py` `Message` ✓
- [x] 6.4 `db/models/document.py` `Document`（meta 列 `JSONB.with_variant(JSON, "sqlite")`） ✓
- [x] 6.5 `db/models/chunk.py` `Chunk`（embedding `Vector(EMBED_DIM).with_variant(_JSONVectorFallback, "sqlite")`） ✓
- [x] 6.6 `db/models/token.py` `RefreshToken` ✓
- [x] 6.7 `db/models/__init__.py` 集中 re-export 6 个模型。

## 7. Alembic 配置

- [x] (adjusted) 7.1 **没有**跑 `alembic init --template async` —— 手写 `alembic.ini` + `alembic/env.py` + `alembic/script.py.mako`（原因：init 生成的 async template 与我们"URL 从 settings 读 + sync/async 兼容"的需求不符）。
- [x] 7.2 `alembic.ini` 没有 `sqlalchemy.url` 行，全由 env.py 处理；带 `post_write_hooks` 让 autogenerate 产物自动过 ruff。
- [x] 7.3 `env.py`：`_db_url()` 优先 CLI `-x url=` → settings；`import db.models` 触发注册；同时支持 `postgresql+asyncpg` / `sqlite+aiosqlite`（async 分支）与 `postgresql://`（sync 分支）；`render_as_batch = is_sqlite(url)`；`compare_type=True`。
- [x] 7.4 `script.py.mako` 标准模板。

## 8. 初始迁移 `0001_init.py`

- [x] (adjusted) 8.1 **手写**迁移（不走 autogenerate）：autogenerate 无法正确生成 `CREATE EXTENSION` / `ivfflat` 语句。
- [x] 8.2 `upgrade()` 先 `CREATE EXTENSION IF NOT EXISTS vector / pg_trgm`（仅 PG）再建表。
- [x] 8.3 `chunks.embedding` 的 `ix_chunks_embedding_ivfflat (vector_cosine_ops, lists=100)` 仅在 PG 上建。
- [x] (adjusted) 8.4 `users.email` 用 `String(255) + unique index` 实现"大小写敏感 unique"；`citext` 留作后续优化（可选）。
- [x] 8.5 `downgrade()` 按 FK 顺序反向 drop 全部表 + 索引；extension 刻意保留（schema-wide，反复 `CREATE IF NOT EXISTS` 幂等）。

## 9. `docker-compose.yml` 加 postgres

- [x] 9.1 新增 `postgres` service，镜像 `pgvector/pgvector:pg16`。
- [x] 9.2 端口 `5432:5432`。
- [x] 9.3 env `POSTGRES_USER=rag POSTGRES_PASSWORD=rag POSTGRES_DB=ragdb`。
- [x] 9.4 volume `pg_data:/var/lib/postgresql/data`。
- [x] 9.5 `profiles: ["db", "web"]`；ollama 也加了 `profiles: ["ollama", "web"]` 让默认 `docker compose up` 不乱启。
- [x] 9.6 `healthcheck: pg_isready -U rag -d ragdb`，interval 5s/retries 10。

## 10. 启动脚本

- [x] 10.1 `scripts/db_init.py` 完成：probe → alembic upgrade head → pg_extension 检查；非 PG 自动跳过 extension 检查。
- [x] 10.2 脚本头部 `sys.path.insert(0, str(_ROOT))`。
- [x] (adjusted) 10.3 本地冒烟 **用 SQLite 代替 docker**（`python scripts/db_init.py sqlite+aiosqlite:///./.db_init_test.db` 通过）；真正的 `docker compose --profile db up -d postgres && python scripts/db_init.py` 需 docker 在手，留给首次使用 PG 的开发者。

## 11. `DBChatMemory`（可选路径）

- [x] (deferred) 11.1 ~11.4 —— 统一推迟到后续小 change `switch-chat-memory-to-db`。本 change 只建 schema + ORM，不触碰 `core/memory/chat_memory.py`；`FileChatMemory` 仍是默认且唯一实现。

## 12. 测试

- [x] 12.1 `tests/conftest.py` 新增 `async_engine`（SQLite in-memory + `Base.metadata.create_all`）与 `async_session` fixture。
- [x] 12.2 `tests/unit/db/test_session.py` + `tests/unit/db/test_models_basic.py` 共 8 条，全部通过。
- [x] (deferred) 12.3 `tests/integration/db/test_pgvector.py` + `@pytest.mark.pg` —— marker 已注册，测试文件交给 P5 一起做。
- [x] (deferred) 12.4 `tests/unit/core/memory/test_db_chat_memory.py` —— 随 §11 一起推迟。
- [x] 12.5 `uv run pytest -q -m "not pg"` 等价于 `uv run pytest -q` → **40 passed**。

## 13. 文档与质量

- [x] (adjusted) 13.1 `docs/ARCHITECTURE.md` 在 v0.4 干净化时被删除；用 `README.md` 新增的 "Database (Postgres + pgvector)" 段 + `AGENTS.md §19 v0.8` 替代。
- [x] 13.2 `README.md` 新增 "Database" 段落，介绍 `make db.up && make db.init`。
- [x] 13.3 `uv run ruff check db/ alembic/` clean（所有 db/ 文件 ruff 零错）。
- [x] 13.4 `uv run mypy --strict . --explicit-package-bases` → **Success: no issues found in 48 source files**。
- [x] 13.5 `AGENTS.md §19` 追加 v0.8 条目。

## 14. 冒烟

- [x] (adjusted) 14.1 `docker compose --profile db config` 通过；实际 `up -d` 需本地 docker daemon，留给使用者。
- [x] 14.2 `scripts/db_init.py` 在 SQLite 上输出完整 4 行 `[db-init] ...`；PG 路径代码一致（仅 extension 校验分支不同）。
- [x] 14.3 `uv run python main.py chat` 仍是 File memory（未切 DB），CLI 启动无回归。
- [x] (adjusted) 14.4 SQLite 下用 `sqlite3` 验证 6 张表 + `alembic_version` 全部建好；真正的 `psql` 验证 `vector(768)` 列与 ivfflat 索引留给实际启动 PG 的使用者。
