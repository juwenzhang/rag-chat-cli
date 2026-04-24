# Proposal: Observability with OpenTelemetry + Prometheus

## Why

AGENTS.md §8 / §15 P10 要求：

> 可观测性：结构化日志（JSON）、`X-Request-ID` 贯穿、OpenTelemetry trace、Prometheus metrics。
> 业务指标：`request_duration_ms`、`llm_latency_ms`、`embedding_latency_ms`、`rag_hits_count`、`tokens_generated_total`。

当前项目：
- 日志不结构化，`print` 散落在 `utils/logger.py`。
- 无 traceId 贯穿，排查跨进程（api ↔ worker ↔ llm）很困难。
- 无 metrics endpoint，运维黑盒。

§15 P10 是"收官"阶段 —— 前面所有功能都就位后，给它装上监控。

## What Changes

### 日志
- 全面切换 `structlog`：JSON 输出 stdout，字段 `ts / level / logger / msg / request_id / user_id / trace_id / span_id / dur_ms`。
- `utils/logger.py` 改为 `configure_logging(settings)` 工厂；移除旧 print-style API。
- `AccessLogMiddleware` 输出结构化；敏感字段继续脱敏（Change 7 已做）。

### Tracing
- 新增 `observability/tracing.py`：
  - `init_tracing(service_name, otlp_endpoint=None)` 配置 OTLP exporter（`OTEL_EXPORTER_OTLP_ENDPOINT` env）。
  - 若未配置 OTLP，默认 `ConsoleSpanExporter`（dev）。
- 自动 instrument：
  - `FastAPIInstrumentor.instrument_app(app)`。
  - `SQLAlchemyInstrumentor.instrument(engine=engine)`。
  - `RedisInstrumentor`.
  - `HTTPXClientInstrumentor`（自动为 Ollama 调用打 span）。
- 自写 span：
  - `core/chat_service.generate` 外层 span；内部为 `llm.chat_stream` 子 span。
  - `core/retrieval.pgvector_store.search` 子 span。
  - `workers/tasks/*` 每个任务一个 span，关联 `job.id`。

### Metrics
- 新增 `observability/metrics.py`：
  - Prometheus 命名约定 + `Registry`。
  - 内置指标：`http_requests_total{method,route,status}`、`http_request_duration_seconds_bucket`、`llm_request_duration_seconds`、`embedding_request_duration_seconds`、`rag_hits{kind}`、`tokens_generated_total{model}`、`auth_login_total{status}`、`rate_limited_total`。
  - 暴露 `GET /metrics` 端点（放 `api/routers/meta.py`）。
- `api/middleware/metrics.py`：`HTTPMetricsMiddleware` 记录 request duration + count。
- `core/chat_service.generate` 统计 tokens 数；`OllamaClient` 统计 llm / embed 延迟。

### Settings
- `settings.observability`：
  - `tracing_enabled / otlp_endpoint / otlp_headers`。
  - `metrics_enabled`。
  - `log_format: "json" | "console"`（dev 可用 console 更易读）。

### docker-compose（可选 profile `obs`）
- 新增 `otel-collector`（镜像 `otel/opentelemetry-collector`），配置收集到 Jaeger。
- 新增 `jaeger`（镜像 `jaegertracing/all-in-one:latest`）。
- 新增 `prometheus`（镜像 `prom/prometheus`），scrape `api:8000/metrics`。
- 默认不启动（`profiles: ["obs"]`）。

## Non-goals

- 不接 Grafana dashboard JSON（先有 Prom + Jaeger，dashboard 按需手工配）。
- 不做 APM 厂商商业集成（Datadog/NewRelic）。
- 不做日志聚合到 Loki / ELK。

## Impact

- **新增**：`observability/` 目录（tracing.py、metrics.py、logging.py）、`api/middleware/metrics.py`、compose `obs` profile 的三个 service、`configs/otel-collector.yaml`、`configs/prometheus.yml`。
- **修改**：`utils/logger.py` 重写、`api/app.py` 注入三件（logging/tracing/metrics）、`workers/context.py` 同。
- **依赖**：`structlog>=24`、`opentelemetry-api>=1.25`、`opentelemetry-sdk`、`opentelemetry-exporter-otlp`、`opentelemetry-instrumentation-fastapi`、`opentelemetry-instrumentation-sqlalchemy`、`opentelemetry-instrumentation-redis`、`opentelemetry-instrumentation-httpx`、`prometheus-client>=0.20`。
- **风险**：中。instrumentor 与 async 兼容要验证；metrics 中间件放错位置会漏计。
- **回退方式**：`settings.observability.tracing_enabled=false` + `metrics_enabled=false` → 所有行为退化；不依赖外部 collector。
