# Design: Observability (structlog + OTel + Prometheus)

## Context

AGENTS.md §8 要求三层可观测性：日志（结构化）、追踪（OTel）、指标（Prometheus）。本 change 是最后一块，需要与所有前置 change 的关键路径集成。

## Goals / Non-Goals

**Goals**
- **零侵入**：`tracing_enabled=false` 时代码路径完全不变（OTel SDK 的 noop tracer）。
- **一致 trace_id**：HTTP 请求 → DB 查询 → LLM 调用 → worker 任务，同一 trace_id 贯穿。
- **业务指标精准**：LLM 延迟、embedding 延迟、RAG hits、token 数，都在 `core/` 层打点，不依赖 HTTP 层。
- **dev 友好**：`LOG_FORMAT=console` 时 structlog 输出彩色可读格式。

**Non-Goals**
- 不做 exemplars（Prometheus 2.x 特性，后续可加）。
- 不做 baggage 传播（只传 trace/span id）。

## Architecture

```
observability/
├── __init__.py
├── logging.py     # configure_logging(settings)
├── tracing.py     # init_tracing(service_name, settings)
└── metrics.py     # Registry + 所有 Counter/Histogram 定义
```

### `observability/logging.py`

```python
def configure_logging(settings: Settings) -> None:
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if settings.observability.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
    # 同时配置 stdlib logging → structlog bridge（让 uvicorn / sqlalchemy 日志也走 structlog）
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    logging.getLogger("uvicorn.access").handlers.clear()
```

每个请求开始时 `structlog.contextvars.bind_contextvars(request_id=..., user_id=...)` → 所有后续 log 自动带这两个字段。

### `observability/tracing.py`

```python
def init_tracing(service_name: str, settings: Settings) -> None:
    if not settings.observability.tracing_enabled:
        return  # noop tracer 自动生效

    resource = Resource.create({SERVICE_NAME: service_name, SERVICE_VERSION: __version__})
    if settings.observability.otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=settings.observability.otlp_endpoint,
                                    headers=settings.observability.otlp_headers)
    else:
        exporter = ConsoleSpanExporter()

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Auto-instrumentation
    FastAPIInstrumentor.instrument()
    SQLAlchemyInstrumentor.instrument()
    RedisInstrumentor.instrument()
    HTTPXClientInstrumentor.instrument()

tracer = trace.get_tracer(__name__)
```

手工 span 示例（`core/chat_service.py`）：

```python
with tracer.start_as_current_span("chat.generate") as span:
    span.set_attribute("session_id", session_id)
    span.set_attribute("use_rag", use_rag)
    # ... 内部 llm span 由 HTTPXClientInstrumentor 自动打
```

### `observability/metrics.py`

```python
from prometheus_client import Counter, Histogram, CollectorRegistry, REGISTRY

# 使用全局 REGISTRY（默认）
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests",
    ["method", "route", "status"]
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request duration",
    ["method", "route"],
    buckets=[.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10]
)
llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds", "LLM chat_stream duration",
    ["model"]
)
embedding_request_duration_seconds = Histogram(
    "embedding_request_duration_seconds", "Embedding request duration",
    ["model"]
)
rag_hits_total = Counter("rag_hits_total", "RAG retrieval hits", ["kind"])  # kind=retrieval/empty
tokens_generated_total = Counter("tokens_generated_total", "Tokens generated", ["model"])
auth_login_total = Counter("auth_login_total", "Auth login attempts", ["status"])  # ok/fail
rate_limited_total = Counter("rate_limited_total", "Rate limited requests", ["route"])
```

### `api/middleware/metrics.py`

```python
class HTTPMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        resp = await call_next(request)
        dur = time.perf_counter() - start
        route = request.scope.get("route", {}).get("path", request.url.path)
        http_requests_total.labels(request.method, route, resp.status_code).inc()
        http_request_duration_seconds.labels(request.method, route).observe(dur)
        return resp
```

### `GET /metrics` 端点

```python
# api/routers/meta.py
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

@router.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

> 注意：`/metrics` 不应暴露给公网；Nginx 配置 `location /metrics { deny all; }` 或 IP 白名单（Change 10 的 nginx.conf 补一行）。

### `core/` 层打点

`OllamaClient.chat_stream`：

```python
with tracer.start_as_current_span("ollama.chat_stream") as span:
    span.set_attribute("model", model)
    t0 = time.perf_counter()
    async for chunk in self._stream(...):
        yield chunk
    llm_request_duration_seconds.labels(model).observe(time.perf_counter() - t0)
```

`OllamaClient.embed`：类似，用 `embedding_request_duration_seconds`。

`ChatService.generate`：

```python
if hits: rag_hits_total.labels("retrieval").inc(len(hits))
else: rag_hits_total.labels("empty").inc()
# done event 后：
tokens_generated_total.labels(model).inc(usage.get("completion_tokens", 0))
```

### Settings

```python
class ObservabilitySettings(BaseModel):
    tracing_enabled: bool = False
    otlp_endpoint: str | None = None
    otlp_headers: dict[str, str] = Field(default_factory=dict)
    metrics_enabled: bool = True
    log_format: Literal["json", "console"] = "console"
```

prod 默认：`LOG_FORMAT=json`、`TRACING_ENABLED=true`、`OTLP_ENDPOINT=http://otel-collector:4317`。

### docker-compose `obs` profile

```yaml
otel-collector:
  image: otel/opentelemetry-collector-contrib:0.103.0
  volumes: ["./configs/otel-collector.yaml:/etc/otelcol-contrib/config.yaml"]
  ports: ["4317:4317", "4318:4318"]
  profiles: ["obs"]
  networks: [ragnet]

jaeger:
  image: jaegertracing/all-in-one:1.58
  ports: ["16686:16686"]
  profiles: ["obs"]
  networks: [ragnet]

prometheus:
  image: prom/prometheus:v2.53.0
  volumes: ["./configs/prometheus.yml:/etc/prometheus/prometheus.yml"]
  ports: ["9090:9090"]
  profiles: ["obs"]
  networks: [ragnet]
```

`configs/otel-collector.yaml`：接收 OTLP → 导出到 Jaeger。
`configs/prometheus.yml`：scrape `api:8000/metrics` 每 15s。

## Alternatives Considered

- **loguru**：比 structlog 更简单，但 structlog 的 contextvars 集成更强，适合 async。
- **OpenMetrics / OTLP metrics**：统一 OTel metrics + traces；本期 Prometheus 更成熟，先用 `prometheus-client`，后续可切 OTel metrics exporter。
- **Sentry**：错误追踪，与 OTel 互补；本期不引入，避免外部依赖。

## Risks & Mitigations

- **风险**：`FastAPIInstrumentor` 与 `BaseHTTPMiddleware` 顺序冲突。
  **缓解**：`FastAPIInstrumentor.instrument_app(app)` 在 `create_app()` 最后调用（所有 middleware 加完之后）。
- **风险**：`SQLAlchemyInstrumentor` 在 async engine 下 span 不正确。
  **缓解**：使用 `opentelemetry-instrumentation-sqlalchemy>=0.46b0`（已支持 async）；单测验证 span 存在。
- **风险**：`/metrics` 暴露内部信息。
  **缓解**：Nginx deny all；API 层可加 IP 白名单 middleware（简单实现）。
- **风险**：structlog 与 uvicorn 的 access log 重复。
  **缓解**：`logging.getLogger("uvicorn.access").handlers.clear()` + `propagate=False`；由 `AccessLogMiddleware` 统一输出。

## Testing Strategy

- 单元：
  - `tests/unit/observability/test_logging.py`：`configure_logging(json)` 后 `logger.info("x", k=1)` 输出可解析 JSON。
  - `tests/unit/observability/test_metrics.py`：`http_requests_total.labels("GET","/health","200").inc()` 后 `generate_latest()` 含该行。
- 集成：
  - `tests/api/test_metrics_endpoint.py`：`GET /metrics` 200，body 含 `http_requests_total`。
  - `tests/api/test_tracing.py`：用 `InMemorySpanExporter` 替换 OTLP，发一个 `/chat/messages` 请求，断言 span 树含 `chat.generate` + `ollama.chat_stream`。
- 冒烟：
  - `docker compose --profile obs up -d`。
  - `curl http://localhost:9090/api/v1/query?query=http_requests_total` 返回非空。
  - Jaeger UI `http://localhost:16686` 能看到 trace。
