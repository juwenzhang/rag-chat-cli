# Redis 三件套接入

后端用 Redis 干三件事：**缓存**、**限流**、**队列**。本文档讲前两件已落地的部分，队列在 `service/workers/queue.py` 里现成等待生产端启用。

> 配套实现：[`service/platform/redis.py`](../../service/platform/redis.py)、[`service/llm/rate_limit.py`](../../service/llm/rate_limit.py)。

---

## 1. 总开关

`REDIS_ENABLED=false` 是默认值——后端**不依赖 Redis 即可启动**。本地 dev 想跑通主链路无需起 daemon。

| 环境变量 | 默认值 | 含义 |
| --- | --- | --- |
| `REDIS_ENABLED` | `false` | 总开关。false 时 cache/限流均退化 no-op |
| `REDIS_URL` | `redis://redis:6379/0` | 连接串，本地常用 `redis://localhost:6379/0` |
| `REDIS_CACHE_DEFAULT_TTL` | `300`（秒） | `cached()` 装饰器默认 TTL |
| `REDIS_LLM_RATE_PER_USER` | `30` | 单用户每窗口允许的 LLM 调用次数 |
| `REDIS_LLM_RATE_WINDOW_S` | `60`（秒） | 限流窗口长度 |

**生产部署必须**把 `REDIS_ENABLED=true` 打开，否则限流不生效（fail-open）。

---

## 2. 客户端单例

```python
from service.platform.redis import get_redis_client, aclose_redis_client

client = await get_redis_client()           # None when disabled
client_must = await get_redis_client(required=True)  # 抛 RedisDisabledError
```

- 进程级单例，懒初始化，从 `settings.redis.redis_url` 读
- FastAPI lifespan 里挂 `aclose_redis_client()`（已在 `api/app.py` 接好）
- 连接 URL 在日志中**自动屏蔽密码**

---

## 3. 缓存：`@cached`

```python
from service.platform.redis import cached

@cached(namespace="provider", ttl=120)
async def get_provider_config(user_id: str, provider_id: str) -> dict:
    # 真实查询，命中缓存时不会执行
    ...
```

设计取舍：

- **失败容错**：Redis 挂了 / 序列化失败一律退到底层函数，绝不阻塞用户
- **key 自动派生**：默认用 `(args, kwargs)` 的 SHA1，自定义传 `key_fn=`
- **JSON 序列化**：返回值必须能被 `json.dumps(..., default=str)` 处理（dataclass、UUID、datetime 都可）
- **过期靠 Redis EXPIRE**：没有手动驱逐路径要维护

⚠️ **不要缓存敏感数据**（token / API key），缓存命名空间不做加密。

---

## 4. 限流：`RedisRateLimiter`

固定窗口计数器（INCR + EXPIRE），按 `namespace:key` 隔离。

```python
from service.platform.redis import RedisRateLimiter

limiter = RedisRateLimiter(namespace="my-feature", limit=10, window_s=60)
allowed, retry_after = await limiter.hit(user_key)
if not allowed:
    raise SomeError(f"retry in {retry_after}s")
```

### LLM 专用快捷方式

`service/llm/rate_limit.py::enforce_user_llm_quota` 把 `RedisRateLimiter` 包好默认配置，路由直接用：

```python
from service.llm.rate_limit import enforce_user_llm_quota

# 在 SSE/WS 流开始前 / REST 端点开头调用
await enforce_user_llm_quota(user_id=str(user.id), provider="openai-prod")
```

超限时抛 `LLMRateLimitError`（带 `retry_after` 字段），**与上游 429 路径完全一致**：

| 入口 | 失败响应 |
| --- | --- |
| REST `POST /chat/messages` | `429 Retry-After: <s>`，`code=llm_rate_limited` |
| SSE `POST /chat/stream` | `error` 事件 `{code: "llm_rate_limited", retry_after: <s>}` |
| WS `/ws/chat` | 同上 SSE 格式 |

---

## 5. 队列（占位）

`service/workers/queue.py::RedisJobQueue` 已就绪（`LPUSH` / `BRPOP`），目前**没有生产端**。计划接入：

- ingestion（大文件分片入向量库）
- 长任务异步化（评测、批量翻译）
- 定时任务（每天对热门会话生成摘要）

启动 worker：`python main.py worker`（待加 CLI 命令）。

---

## 6. 失效与降级

| 故障 | 行为 |
| --- | --- |
| Redis daemon 挂 | cache miss / 限流 fail-open / 仅日志 warning，**不影响请求** |
| `REDIS_ENABLED=false` | 同上，所有 helper 静默 no-op |
| 序列化失败 | 跳过缓存写入 / 命中后失败回源 |
| 窗口边缘突发 | 固定窗口算法的已知缺陷（最坏 2× limit），需要严格滑动窗口可改实现，API 不变 |

---

## 7. 与刚落地的错误码体系咬合

`LLMRateLimitError.code = "llm_rate_limited"`（`service/llm/client.py`）

→ REST 走 `api/middleware/errors.py::_handle_llm` 映射 `429 + Retry-After`

→ SSE/WS 直接拼 `ErrorEvent(code=type(exc).code, retry_after=exc.retry_after)`

→ 前端 `ErrorCode.LLM_RATE_LIMITED` 分支提示用户「调用太频繁，N 秒后再试」

完整错误码表见 [`ERROR_CODES.md`](ERROR_CODES.md)。
