# Tasks: Redis + Background Workers (arq)

## 1. 依赖

- [ ] 1.1 `pyproject.toml` 新增：`redis>=5.0`、`arq>=0.25`。
- [ ] 1.2 dev 新增：`fakeredis>=2.21`（用于单测）。
- [ ] 1.3 `uv sync` 成功。

## 2. Settings 扩展

- [ ] 2.1 `settings.redis.url`（默认 `redis://localhost:6379/0`）。
- [ ] 2.2 `settings.queue`：`backend / max_jobs / job_timeout / keep_result_seconds`。
- [ ] 2.3 `settings.rate_limit`：`enabled / rules`。
- [ ] 2.4 `.env.example` 同步新增。

## 3. Redis 客户端

- [ ] 3.1 `core/cache/__init__.py`。
- [ ] 3.2 `core/cache/redis.py`：`init_redis / get_redis / dispose_redis`。
- [ ] 3.3 `api/app.py` 的 lifespan 调 `init_redis` 并在 shutdown `dispose_redis`。
- [ ] 3.4 `/health` 端点增加 `redis: ok/fail`、`db: ok/fail` 分项。

## 4. Queue 抽象

- [ ] 4.1 `core/queue/__init__.py`。
- [ ] 4.2 `core/queue/base.py` 定义 `Queue` Protocol。
- [ ] 4.3 `core/queue/client.py`：
  - `ArqQueue.from_settings() -> ArqQueue`。
  - `InlineQueue` + `_INLINE_REGISTRY` 装饰器 `@register_inline("task_name")`。
  - `build_queue() -> Queue` 按 `settings.queue.backend` 选择。
- [ ] 4.4 `core/queue/errors.py`：`QueueError / EnqueueFailedError`。
- [ ] 4.5 单测：`tests/unit/core/queue/test_inline_queue.py`。

## 5. Workers 目录

- [ ] 5.1 `workers/__init__.py`：`WorkerSettings` 类（arq 期望的）。
- [ ] 5.2 `workers/context.py`：`on_startup / on_shutdown`。
- [ ] 5.3 `workers/tasks/__init__.py`（空）。
- [ ] 5.4 `workers/tasks/ingest.py`：`ingest_document(ctx, document_id)` 骨架，embed 留 TODO 给 Change 9。
- [ ] 5.5 `workers/tasks/train.py`：把 `scripts/lora_train.py` 的 main 逻辑改为 `run_lora_training(ctx, config_path)`；原 script 改为 `asyncio.run(run_lora_training(None, args.config))`。
- [ ] 5.6 `workers/tasks/periodic.py`：`daily_reindex` / `purge_expired_refresh_tokens`。
- [ ] 5.7 同一任务函数同时用 `@register_inline("ingest_document")` 装饰（供 inline queue 反查）。

## 6. Rate limit 中间件

- [ ] 6.1 `api/middleware/rate_limit.py`：`RateLimiter` + `RateLimitMiddleware`。
- [ ] 6.2 规则解析：`[{path: "/auth/login", method: "POST", limit: 5, window: 60}]`，支持 path prefix（`startswith`）或精确匹配。
- [ ] 6.3 用 Redis `INCR` + `EXPIRE`（fixed window）；429 时 `Retry-After = remaining_window`。
- [ ] 6.4 `api/app.py` 的 `create_app` 中：`if settings.rate_limit.enabled: app.add_middleware(RateLimitMiddleware, ...)`。
- [ ] 6.5 默认规则（写 `settings.py` 的 `model_validator` 里填充）：
  - `POST /auth/login` 5/min。
  - `POST /auth/register` 5/min。
  - `POST /chat/messages` 30/min。
  - `POST /chat/stream` 30/min。

## 7. CLI `worker` 子命令

- [ ] 7.1 `app/cli.py` 新增 `worker` 子解析器（无参或 `--verbose`）。
- [ ] 7.2 内部 `from arq.worker import run_worker; run_worker(WorkerSettings)`。
- [ ] 7.3 `python main.py worker --help` 正常展示。

## 8. API reindex 实装

- [ ] 8.1 `api/routers/knowledge.py` 的 `/documents:reindex`：
  - 找出当前 user 的全部 document。
  - `for doc in docs: await queue.enqueue("ingest_document", str(doc.id))`。
  - 返回 `{"ok": True, "enqueued": N, "job_ids": [...]}`（仍 202）。
- [ ] 8.2 `get_queue` dependency 注入（从 app.state 拿）。

## 9. `utils/task_scheduler.py` 迁移

- [ ] 9.1 其中"定时重训练"相关代码移到 `workers/tasks/periodic.py` 的新 cron。
- [ ] 9.2 `utils/task_scheduler.py` 保留 deprecated 类壳 + `DeprecationWarning`。
- [ ] 9.3 `main.py` / CLI 原先调 scheduler 的路径改为：生产用 `python main.py worker`；dev 提示 "use inline queue or run `worker`"。

## 10. docker-compose

- [ ] 10.1 新增 `redis` service：`image: redis:7-alpine`，端口 `6379:6379`，`profiles: ["web"]`。
- [ ] 10.2 `healthcheck: redis-cli ping`。
- [ ] 10.3 `api` / `worker` service 占位（Change 10 补真正 Dockerfile）。

## 11. 测试

- [ ] 11.1 `tests/unit/core/queue/test_inline_queue.py`。
- [ ] 11.2 `tests/unit/api/middleware/test_rate_limit.py`（fakeredis）。
- [ ] 11.3 `tests/unit/workers/test_purge_expired.py`、`test_ingest_stub.py`。
- [ ] 11.4 `tests/integration/workers/test_arq_flow.py`（`@pytest.mark.redis`）。
- [ ] 11.5 `tests/api/test_reindex_enqueue.py`：inline 模式，`POST /documents:reindex` 后断言 `ingest_document` 被调用 N 次。
- [ ] 11.6 `uv run pytest -q -m "not redis"` 全绿。

## 12. 质量与文档

- [ ] 12.1 `ruff check core/cache core/queue workers api/middleware/rate_limit.py` 无错。
- [ ] 12.2 `mypy --strict core/queue workers` 无错。
- [ ] 12.3 `docs/OPERATIONS.md` 新增"启动 worker / 配置 rate limit"章节。
- [ ] 12.4 AGENTS.md §19 追加 "Redis + arq workers + rate limit"。

## 13. 冒烟

- [ ] 13.1 `docker compose --profile web up -d redis postgres`。
- [ ] 13.2 `QUEUE__BACKEND=redis python main.py worker` 启动；日志打印 `ready, max_jobs=8`。
- [ ] 13.3 `python main.py serve` + `POST /knowledge/documents:reindex` → worker 日志出现 `ingest.done`。
- [ ] 13.4 连续 6 次 `POST /auth/login` 错误密码 → 第 6 次返回 429 + `Retry-After`。
