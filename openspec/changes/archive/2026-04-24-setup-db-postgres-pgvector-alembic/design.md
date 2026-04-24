# Design: PostgreSQL + pgvector + SQLAlchemy async + Alembic

## Context

AGENTS.md §4、§14、§15 P4 共同约束了本次设计：
- §4：PG15+ / pgvector / SQLAlchemy 2.x async / asyncpg / Alembic。
- §14：核心表 `users / sessions / messages / documents / chunks / tokens`，`chunks.embedding VECTOR(dim)`。
- §15 P4：是 FastAPI / JWT / RAG 的前置。

需要在**不影响现有 CLI** 的前提下，把 DB 层插入项目。

## Goals / Non-Goals

**Goals**
- 零侵入：本次合并后 `python main.py chat` 不依赖 DB 仍能跑（File memory）。
- async-first：所有 engine / session / 模型操作走 `AsyncSession`。
- 幂等迁移：`alembic upgrade head` 可重复执行；`CREATE EXTENSION IF NOT EXISTS vector`。
- 向量维度可配：`settings.retrieval.embed_dim` 默认 768，迁移脚本使用此值。
- 开发体验：`make db-up` / `make db-migrate` / `make db-revision m="..."`（下个 change 做 Makefile 时补）。

**Non-Goals**
- 不写业务 CRUD（Repository 模式下沉到 `core/` 的各服务里，由各自 change 处理）。
- 不做读写分离 / 分片。

## Architecture

```
db/
├── __init__.py
├── base.py           # DeclarativeBase + naming convention + metadata
├── session.py        # engine_factory + async_sessionmaker + get_session
└── models/
    ├── __init__.py   # re-export 所有 model，供 alembic autogenerate 扫描
    ├── _mixins.py    # TimestampMixin / UUIDMixin
    ├── user.py
    ├── session.py    # ChatSession（表名 chat_sessions 避免与 SQLAlchemy Session 冲突）
    ├── message.py
    ├── document.py
    ├── chunk.py
    └── token.py      # RefreshToken / ApiKey
alembic/
├── env.py
├── script.py.mako
└── versions/
    └── 0001_init.py
alembic.ini
```

### `db/base.py`

```python
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# PostgreSQL naming convention（Alembic autogenerate 生成可预测的约束名）
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

### `db/session.py`

```python
_engine: AsyncEngine | None = None
_SessionLocal: async_sessionmaker[AsyncSession] | None = None

def init_engine(url: str | None = None, *, echo: bool = False) -> AsyncEngine:
    global _engine, _SessionLocal
    url = url or settings.db.database_url
    _engine = create_async_engine(
        url, echo=echo, pool_size=settings.db.pool_size,
        pool_recycle=settings.db.pool_recycle, pool_pre_ping=True,
    )
    _SessionLocal = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine

async def get_session() -> AsyncIterator[AsyncSession]:
    assert _SessionLocal is not None, "call init_engine() first"
    async with _SessionLocal() as s:
        yield s

async def dispose_engine() -> None:
    if _engine: await _engine.dispose()
```

### 模型草图

```python
# _mixins.py
class UUIDMixin:
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

# user.py
class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))  # bcrypt，Change 5 使用
    display_name: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(default=True)

# session.py （表名 chat_sessions）
class ChatSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chat_sessions"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str | None] = mapped_column(String(256))

# message.py
class Message(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    session_id: Mapped[UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user/assistant/system
    content: Mapped[str] = mapped_column(Text)
    tokens: Mapped[int | None] = mapped_column(Integer)

# document.py
class Document(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    source: Mapped[str] = mapped_column(String(512))
    title: Mapped[str | None] = mapped_column(String(256))
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)

# chunk.py
from pgvector.sqlalchemy import Vector
class Chunk(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chunks"
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))  # 768 默认
    token_count: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (
        Index("ix_chunks_embedding_ivfflat", "embedding",
              postgresql_using="ivfflat",
              postgresql_ops={"embedding": "vector_cosine_ops"},
              postgresql_with={"lists": 100}),
    )

# token.py
class RefreshToken(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "refresh_tokens"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column()
    revoked_at: Mapped[datetime | None] = mapped_column()
```

### Alembic 配置

`alembic/env.py` 关键点：

```python
from db.base import Base
import db.models  # 触发 model 注册
target_metadata = Base.metadata

def run_migrations_online() -> None:
    # async driver
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    async def _do() -> None:
        async with connectable.connect() as conn:
            await conn.run_sync(do_run_migrations)
    asyncio.run(_do())
```

初始 migration `0001_init.py`：

```python
def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # op.create_table(...) for each model
    # create ivfflat index on chunks.embedding
```

### 配置扩展（若 Change 1 里未含）

```python
class DBSettings(BaseModel):
    database_url: str
    pool_size: int = 10
    pool_recycle: int = 1800
    echo_sql: bool = False
```

### SQLite fallback for CI

- 在 `tests/conftest.py` 中检测若 `DB__DATABASE_URL` 以 `sqlite` 开头，`Chunk.embedding` 改为 `JSON`（用 `TypeDecorator` 做类型切换）。
- 不跑涉及 ivfflat 索引的测试（`@pytest.mark.pg`）。

## Alternatives Considered

- **SQLModel**：更轻，但生态不如 SQLAlchemy 2.x 成熟；AGENTS.md §1 已定 SQLAlchemy 2.x。
- **yoyo-migrations / atlas**：Alembic 是 SQLAlchemy 官方标配，文档/社区最成熟。

## Risks & Mitigations

- **pgvector 维度写死**：后期换 embedding 模型会不兼容。
  **缓解**：迁移用 `EMBED_DIM = settings.retrieval.embed_dim`，后续换维度用新 migration `ALTER` 或新建列。
- **Alembic async 脚本初学者踩坑**：提供 README + `scripts/db_init.py` 包装。
- **CI 无 docker**：SQLite fallback 已给出方案。

## Testing Strategy

- 单元：
  - `tests/unit/db/test_session.py`：`init_engine("sqlite+aiosqlite:///:memory:")`，能 `get_session()` 拿到可用会话。
  - `tests/unit/db/test_models_basic.py`：用 SQLite 建 User / ChatSession / Message 三表（skip Chunk），insert + select round-trip。
- 集成（需 docker）：
  - `@pytest.mark.pg tests/integration/db/test_pgvector.py`：起 PG 容器，`alembic upgrade head`，insert Chunk，做 `ORDER BY embedding <=> ...` 查询。
- 冒烟：
  - `make db-up && alembic upgrade head`（Makefile change 后补齐命令）。
  - `psql -c "SELECT extname FROM pg_extension"` 能看到 `vector`。
