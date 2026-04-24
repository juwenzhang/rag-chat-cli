# Tasks: Observability (structlog + OTel + Prometheus)

## 1. 依赖

- [ ] 1.1 `pyproject.toml` 新增：
  - `structlog>=24.2`。
  - `opentelemetry-api>=1.25`、`opentelemetry-sdk`、`opentelemetry-exporter-otlp-proto-grpc`。
  - `opentelemetry-instrumentation-fastapi`、`opentelemetry-instrumentation-sqlalchemy`、`opentelemetry-instrumentation-redis`、`opentelemetry-instrumentation-httpx`。
  - `prometheus-client>=0.20`。
- [ ] 1.2 dev 新增：`opentelemetry-sdk` 的 `InMemorySpanExporter`（已含在 sdk 中）。
- [ ] 1.3 `uv sync` 成功。

## 2. Settings 扩展

- [ ] 2.1 `settings.observability`：`tracing_enabled / otlp_endpoint / otlp_headers / metrics_enabled / log_format`。
- [ ] 2.2 `.env.example` 补 `OBSERVABILITY__LOG_FORMAT=json`、`OBSERVABILITY__TRACING_ENABLED=false`。
- [ ] 2.3 prod 模式下 `log_format` 默认 `json`（通过 `model_validator` 或 `default_factory`）。

## 3. 结构化日志

- [ ] 3.1 新建 `observability/__init__.py`。
- [ ] 3.2 `observability/logging.py`：`configure_logging(settings)` 按 design。
- [ ] 3.3 `utils/logger.py` 改为：
  ```python
  import structlog
  logger = structlog.get_logger()
  # 保留 get_logger() 函数供旧代码调用，内部返回 structlog.get_logger()
  ```
- [ ] 3.4 全局搜索 `print(` 替换为 `logger.info/debug/warning`（除 `scripts/` 和 `tests/`）。
- [ ] 3.5 `api/app.py` lifespan 最早调 `configure_logging(settings)`。
- [ ] 3.6 `app/cli.py` 入口调 `configure_logging(settings)`（CLI 默认 console 格式）。
- [ ] 3.7 `workers/context.py` on_startup 调 `configure_logging(settings)`。
- [ ] 3.8 `AccessLogMiddleware` 改为 `structlog.get_logger("access").info(...)` 输出结构化字段。
- [ ] 3.9 单测：`configure_logging(json)` → `logger.info("test", k=1)` → 捕获 stdout → JSON 解析成功。

## 4. Tracing

- [ ] 4.1 `observability/tracing.py`：`init_tracing(service_name, settings)` + `tracer = trace.get_tracer(__name__)`。
- [ ] 4.2 `api/app.py` lifespan 调 `init_tracing("rag-chat-api", settings)`。
- [ ] 4.3 `workers/context.py` on_startup 调 `init_tracing("rag-chat-worker", settings)`。
- [ ] 4.4 `core/chat_service.py` 手工 span `chat.generate`（含 session_id / use_rag 属性）。
- [ ] 4.5 `core/llm/ollama.py` 手工 span `ollama.chat_stream` / `ollama.embed`（含 model 属性）。
- [ ] 4.6 `core/retrieval/pgvector_store.py` 手工 span `pgvector.search`（含 top_k / query_len 属性）。
- [ ] 4.7 `workers/tasks/ingest.py` 手工 span `worker.ingest_document`（含 document_id）。
- [ ] 4.8 `structlog.contextvars.bind_contextvars(trace_id=..., span_id=...)` 在 span 内调用，让日志自动带 trace 上下文。
- [ ] 4.9 单测：`InMemorySpanExporter` 替换 OTLP，发一个 chat 请求，断言 span 名称列表含 `chat.generate`。

## 5. Prometheus Metrics

- [ ] 5.1 `observability/metrics.py`：按 design 定义所有 Counter / Histogram。
- [ ] 5.2 `api/middleware/metrics.py`：`HTTPMetricsMiddleware`。
- [ ] 5.3 `api/app.py` 注册 `HTTPMetricsMiddleware`（在 `AccessLogMiddleware` 之后）。
- [ ] 5.4 `api/routers/meta.py`：`GET /metrics` 端点（`include_in_schema=False`）。
- [ ] 5.5 `api/app.py` 挂 `meta_router`（prefix=""）。
- [ ] 5.6 `core/llm/ollama.py` 在 `chat_stream` / `embed` 完成后 observe histogram。
- [ ] 5.7 `core/chat_service.py` 在 `done` 事件后 `tokens_generated_total.inc(usage.completion_tokens)`。
- [ ] 5.8 `core/auth/service.py` 在 `login` 成功/失败后 `auth_login_total.labels(status).inc()`。
- [ ] 5.9 `api/middleware/rate_limit.py` 在 429 时 `rate_limited_total.labels(route).inc()`。
- [ ] 5.10 单测：`test_metrics_endpoint.py`（`GET /metrics` 200 + 含 `http_requests_total`）。

## 6. Nginx `/metrics` 保护

- [ ] 6.1 `docker/nginx.conf` 新增：
  ```nginx
  location /metrics { deny all; return 403; }
  ```
- [ ] 6.2 或改为 IP 白名单（`allow 10.0.0.0/8; deny all;`）。

## 7. docker-compose `obs` profile

- [ ] 7.1 `docker-compose.yml` 新增 `otel-collector / jaeger / prometheus` 三个 service（profile `obs`）。
- [ ] 7.2 新建 `configs/otel-collector.yaml`：
  ```yaml
  receivers: { otlp: { protocols: { grpc: {}, http: {} } } }
  exporters: { jaeger: { endpoint: "jaeger:14250", tls: { insecure: true } } }
  service: { pipelines: { traces: { receivers: [otlp], exporters: [jaeger] } } }
  ```
- [ ] 7.3 新建 `configs/prometheus.yml`：
  ```yaml
  global: { scrape_interval: 15s }
  scrape_configs:
    - job_name: rag-chat-api
      static_configs: [{ targets: ["api:8000"] }]
  ```
- [ ] 7.4 `docker compose --profile obs up -d` 成功启动。

## 8. 测试

- [ ] 8.1 `tests/unit/observability/test_logging.py`。
- [ ] 8.2 `tests/unit/observability/test_metrics.py`。
- [ ] 8.3 `tests/api/test_metrics_endpoint.py`。
- [ ] 8.4 `tests/api/test_tracing.py`（InMemorySpanExporter）。
- [ ] 8.5 `uv run pytest -q -k "observ or metrics or tracing"` 绿。

## 9. 质量

- [ ] 9.1 `ruff check observability/` 无错。
- [ ] 9.2 `mypy --strict observability/` 无错。
- [ ] 9.3 `make ci` 全绿（含新测试）。

## 10. 文档

- [ ] 10.1 `docs/OPERATIONS.md` 补"可观测性"章节：
  - 如何启动 obs profile。
  - Jaeger UI 查 trace。
  - Prometheus 查 metrics。
  - 常用 PromQL：`rate(http_requests_total[5m])`、`histogram_quantile(0.99, llm_request_duration_seconds_bucket)`。
- [ ] 10.2 AGENTS.md §19 追加 "Observability: structlog + OTel + Prometheus"。

## 11. 冒烟

- [ ] 11.1 `docker compose --profile web up -d`：`curl http://localhost:8000/metrics` 返回 Prometheus 格式文本，含 `http_requests_total`。
- [ ] 11.2 发几条聊天请求后，`curl 'http://localhost:8000/metrics' | grep llm_request_duration` 有数据。
- [ ] 11.3 `docker compose --profile obs up -d`：
  - Jaeger UI `http://localhost:16686` 能看到 `rag-chat-api` service 的 trace。
  - Prometheus `http://localhost:9090` 能查到 `http_requests_total`。
- [ ] 11.4 `LOG_FORMAT=json python main.py serve` 输出 JSON 日志，`jq .` 可解析。
- [ ] 11.5 `LOG_FORMAT=console python main.py chat` 输出彩色可读日志。
