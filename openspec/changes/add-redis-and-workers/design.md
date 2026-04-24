# Design: Redis + Background Workers (arq)

## Context

AGENTS.md §1 选 `arq`（asyncio-native）；§7 给出任务清单；§10 给出限流规则（登录 5/min、chat 30/min/user）。Change 4 DB + Change 5 Auth + Change 6 API 已经就位，本次补齐"异步能力 + 缓存 + 限流"三大基础设施。

## Goals / Non-Goals

**Goals**
- **单进程 dev / 多进程 prod 两套模式**：`QUEUE__BACKEND=inline` 直接同步执行；`redis` 走 arq。
- **统一 queue client**：API/CLI 调用同一 `ArqQueue.enqueue`，底层根据配置分发。
- **worker 独立进程**：`python main.py worker` 等价 `arq workers.WorkerSettings`。
- **Redis 作为 rate limit + cache + broker** 三合一。
- **可观测**：任务 enqueue / start / finish / error 都打 structured log + metric。

**Non-Goals**
- 不做优先级队列（用单一 default queue 足够）。
- 不做 Saga / 分布式事务。

## Architecture

```
core/
├── cache/
│   ├── __init__.py
│   └── redis.py           # async singleton + ping
└── queue/
    ├── __init__.py
    ├── client.py          # ArqQueue / InlineQueue
    ├── base.py            # Queue Protocol
    └── errors.py

workers/
├── __init__.py            # WorkerSettings = arq 入口
├── context.py             # startup/shutdown：init_engine + redis + httpx
└── tasks/
    ├── __init__.py
    ├── ingest.py          # ingest_document(document_id)
    ├── train.py           # run_lora_training(config_path)
    └── periodic.py        # daily_reindex, purge_expired_refresh_tokens

api/middleware/rate_limit.py
```

### `core/cache/redis.py`

```python
_redis: Redis | None = None

def init_redis(url: str | None = None) -> Redis:
    global _redis
    _redis = Redis.from_url(url or settings.redis.url, decode_responses=True)
    return _redis

def get_redis() -> Redis:
    assert _redis is not None
    return _redis

async def dispose_redis() -> None:
    if _redis: await _redis.aclose()
```

### `core/queue/base.py`

```python
class Queue(Protocol):
    async def enqueue(self, task_name: str, *args, **kwargs) -> str: ...
    async def aclose(self) -> None: ...
```

### `core/queue/client.py`

```python
class ArqQueue(Queue):
    def __init__(self, pool: ArqRedis): self._pool = pool

    @classmethod
    async def from_settings(cls, s=None) -> "ArqQueue":
        s = s or settings
        pool = await create_pool(RedisSettings.from_dsn(s.redis.url))
        return cls(pool)

    async def enqueue(self, task_name, *args, **kwargs) -> str:
        job = await self._pool.enqueue_job(task_name, *args, **kwargs)
        return job.job_id

    async def aclose(self): await self._pool.aclose()

class InlineQueue(Queue):
    """dev 模式：直接调用注册的函数，保持 await 语义。"""
    def __init__(self, registry: dict[str, Callable[..., Awaitable]]): self._reg = registry
    async def enqueue(self, task_name, *args, **kwargs) -> str:
        fn = self._reg[task_name]
        await fn(None, *args, **kwargs)  # ctx=None
        return "inline-" + uuid4().hex
    async def aclose(self): pass

def build_queue() -> Queue:
    if settings.queue.backend == "inline":
        return InlineQueue(registry=_INLINE_REGISTRY)
    return asyncio.run(ArqQueue.from_settings())  # 实际在 api lifespan 中 await
```

### `workers/__init__.py`（arq 入口）

```python
from .tasks import ingest, train, periodic
from .context import on_startup, on_shutdown

class WorkerSettings:
    functions = [
        ingest.ingest_document,
        train.run_lora_training,
        periodic.daily_reindex,
        periodic.purge_expired_refresh_tokens,
    ]
    cron_jobs = [
        cron(periodic.daily_reindex, hour=3, minute=0),
        cron(periodic.purge_expired_refresh_tokens, hour=4, minute=0),
    ]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis.url)
    max_jobs = settings.queue.max_jobs
    job_timeout = settings.queue.job_timeout
    keep_result = settings.queue.keep_result_seconds
```

### `workers/context.py`

```python
async def on_startup(ctx: dict) -> None:
    init_engine(settings.db.database_url)
    ctx["redis"] = init_redis(settings.redis.url)
    ctx["http"] = httpx.AsyncClient(timeout=60)

async def on_shutdown(ctx: dict) -> None:
    await ctx["http"].aclose()
    await dispose_redis()
    await dispose_engine()
```

### Tasks 骨架

`workers/tasks/ingest.py`：

```python
async def ingest_document(ctx: dict, document_id: str) -> dict:
    async with SessionLocal() as s:
        doc = await s.get(Document, UUID(document_id))
        if not doc: return {"ok": False, "reason": "not found"}
    # TODO: split + embed (Change 9)
    logger.info("ingest.done", document_id=document_id)
    return {"ok": True}
```

`workers/tasks/periodic.py`：

```python
async def purge_expired_refresh_tokens(ctx: dict) -> int:
    async with SessionLocal() as s:
        result = await s.execute(
            delete(RefreshToken).where(RefreshToken.expires_at < func.now())
        )
        await s.commit()
    return result.rowcount
```

### Rate limit 中间件

`api/middleware/rate_limit.py`：

```python
class RateLimiter:
    """Fixed window + token bucket 混合：
    - 每个 user_id（匿名用 IP）独立 bucket。
    - 规则按 route pattern 配置：
        '/auth/login': 5 / minute
        '/chat/messages': 30 / minute
        '/chat/stream':   30 / minute
    """

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, redis: Redis, rules: list[RateLimitRule]): ...
    async def dispatch(self, request, call_next):
        # 找到匹配规则 → INCR window key → 超过 limit 则 429
```

响应头：`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`，429 时 `Retry-After`。

### Settings

```python
class RedisSettings_(BaseModel):
    url: str = "redis://localhost:6379/0"

class QueueSettings(BaseModel):
    backend: Literal["inline", "redis"] = "inline"
    max_jobs: int = 8
    job_timeout: int = 600
    keep_result_seconds: int = 3600

class RateLimitSettings(BaseModel):
    enabled: bool = False
    rules: list[dict] = Field(default_factory=list)  # 路由 → 规则
```

### CLI `worker` 子命令

```python
case "worker":
    from arq.worker import run_worker
    run_worker(settings_cls=WorkerSettings)
```

## Alternatives Considered

- **Celery**：生态最大，但 async 支持差；本项目全链路 async，arq 更对味。
- **Dramatiq**：async 支持优于 Celery 但弱于 arq；arq 与 FastAPI 生态贴合更紧。
- **RQ**：同步为主。

## Risks & Mitigations

- **风险**：dev 忘装 Redis 报错 → 体验差。
  **缓解**：`QUEUE__BACKEND=inline` 默认，零依赖跑通 reindex 链路。
- **风险**：arq pool 在 FastAPI lifespan 中 create / dispose 时机。
  **缓解**：`api/app.py` lifespan 统一管理 `redis / engine / queue` 三件。
- **风险**：rate limit 规则在代码里写死不灵活。
  **缓解**：从 `settings.rate_limit.rules` 读取，运维侧可改 env。
- **风险**：worker 与 api 对同一 DB 做迁移/写入引发锁。
  **缓解**：worker 所有事务显式 `BEGIN/COMMIT`，不做长事务。

## Testing Strategy

- 单元：
  - `tests/unit/core/queue/test_inline_queue.py`：注册 fn → enqueue → 被调用。
  - `tests/unit/workers/test_purge_expired.py`：SQLite + 造数据 → run → rowcount 正确。
  - `tests/unit/api/middleware/test_rate_limit.py`：fakeredis 模拟，超额触发 429。
- 集成（需 Redis docker）：
  - `@pytest.mark.redis tests/integration/workers/test_arq_flow.py`：真实 Redis + `ArqQueue.enqueue("ingest_document", id)` + 启 worker 跑 1 秒 → 断言日志/结果。
- 冒烟：
  - `docker compose --profile web up -d redis postgres` → `python main.py worker` 启动正常 → `python main.py serve` 下 `POST /knowledge/documents:reindex` 返回 202 + 任务 id。
