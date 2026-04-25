# Proposal: Add Redis + Background Workers (arq)

## Why

AGENTS.md §1 / §7 / §8 / §10 多处依赖 Redis 与后台 worker：

- §1：缓存/限流/广播 → Redis。
- §7：重建索引、文档解析、向量化、定时训练 → 用 **arq** 跑 Python 任务队列（对 async 友好）。
- §8：OpenTelemetry metrics + 业务指标（`request_duration_ms`、`llm_latency_ms` 等）聚合需要 Redis/Prom。
- §10：API rate limit，Token bucket 基于 Redis。

当前 `utils/task_scheduler.py` 只是一个**进程内** APScheduler，既不能多实例扩展，也无法跟 Web 业务分进程。§15 P5-P6 需要"上传文档 → 异步切块 → 向量化"的非阻塞链路；必须引入真正的 broker。

## What Changes

- 新增 `workers/` 目录（§2）：
  - `workers/__init__.py` — arq settings 工厂。
  - `workers/tasks/ingest.py` — 文档解析 + 切块 + embedding（embedding 实现在 Change 9，本次先占位调用 `NotImplementedError` 或 noop）。
  - `workers/tasks/train.py` — 迁移 `scripts/lora_train.py` 的核心编排为可入队任务。
  - `workers/tasks/periodic.py` — cron 任务（示例：每日重建索引、清理过期 refresh token）。
- 新增 `core/queue/`（client SDK）：
  - `core/queue/client.py` — `ArqQueue.enqueue(task_name, **kwargs)`，API/CLI 侧调用。
  - `core/queue/errors.py`。
- 新增 Redis 抽象 `core/cache/redis.py`：
  - `get_redis() -> Redis` 单例（异步 `redis.asyncio`）。
  - 健康检查 `await r.ping()` 暴露给 `/health`。
- 新增 rate limit 中间件 `api/middleware/rate_limit.py`（Token bucket over Redis）。
- 新增 CLI 子命令 `python main.py worker [--queue=default]` → 调 `arq workers.WorkerSettings` 启动。
- `docker-compose.yml` 新增 `redis` service（image `redis:7-alpine`，profile `web`）。
- 迁移 `utils/task_scheduler.py`：
  - 定时任务部分搬到 `workers/tasks/periodic.py`；
  - 进程内调度的同步 API 保留，内部改为"本地模式"（无 Redis 时回退），dev 体验友好。
- API 端 `/knowledge/documents:reindex` 由 Change 6 的 `202` 占位改为**真正入队**。

## Non-goals

- 不实现向量化逻辑（Change 9 做）。
- 不做 Celery（选 arq 更贴 asyncio）。
- 不做分布式追踪（`otel` 在 Change 11 接入）。
- 不做 worker 自动伸缩 / k8s HPA（运维领域）。

## Impact

- **新增**：`workers/`、`core/queue/`、`core/cache/redis.py`、`api/middleware/rate_limit.py`、`scripts/worker.py`（可选）。
- **修改**：`settings.py`（补 `redis / queue / rate_limit` 配置）、`docker-compose.yml`、`api/routers/knowledge.py`（reindex 入队）、`app/cli.py`（`worker` 子命令）。
- **依赖**：`redis>=5.0`（async via `redis.asyncio`）、`arq>=0.25`。
- **风险**：中高。引入独立进程类型；必须提供 dev 的 compose 一键启动。
- **回退方式**：设置 `QUEUE__BACKEND=inline`（内联执行，不入队）；`git revert` 移除 worker 子命令与 redis service。
