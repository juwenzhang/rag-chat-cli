# Capability: `settings`

> **Status**: active
> **Introduced by**: change `bootstrap-settings-and-env`（已归档）
> **Owners**: platform / backend

## 1. Purpose

`settings` 是仓库的**唯一应用级配置入口**。它集中声明所有运行时参数、做类型校验、
并以单例方式提供给所有其他模块使用。

任何模块（CLI、FastAPI、worker、test、脚本）都必须通过 `from settings import settings`
获取配置；**禁止**直接读 `os.environ` 或读写项目里的自定义配置文件（AGENTS.md §7 / §16）。

## 2. Public API

### 2.1 导出

- 模块：`settings`（仓库根 `settings.py`）。
- 导出：`__all__ = ["settings", "Settings"]`
  - `settings`：module-level 单例，类型 `Settings`。
  - `Settings`：`pydantic_settings.BaseSettings` 子类；暴露 `classmethod load() -> Settings`。

### 2.2 使用范例

```python
from settings import settings

base_url = settings.ollama.base_url
top_k = settings.retrieval.top_k
jwt_secret = settings.auth.jwt_secret  # 生产环境必须是强随机值
```

## 3. 分组与字段

七个分组（均为 `pydantic.BaseModel`）：

| 分组         | 必填字段       | 默认值                                                                                                |
| ------------ | -------------- | ----------------------------------------------------------------------------------------------------- |
| `app`        | —              | `env="dev"`, `log_level="INFO"`, `request_id_header="X-Request-ID"`                                   |
| `auth`       | `jwt_secret`   | `jwt_alg="HS256"`, `access_token_ttl_min=15`, `refresh_token_ttl_day=7`                               |
| `db`         | —              | `database_url="postgresql+asyncpg://rag:rag@postgres:5432/ragdb"`                                      |
| `redis`      | —              | `redis_url="redis://redis:6379/0"`                                                                    |
| `ollama`     | —              | `base_url="http://ollama:11434"`, `chat_model="qwen2.5:1.5b"`, `embed_model="nomic-embed-text"`, `timeout=120` |
| `retrieval`  | —              | `enabled=True`, `top_k=4`, `min_score=0.25`                                                           |
| `rate_limit` | —              | `per_min=60`                                                                                          |

分组之间**正交**（互不引用）；跨域组合（如"把 `auth.jwt_secret` 与 `db.database_url` 拼成 DSN"）
必须由调用方完成，`Settings` 本身不做。

## 4. 环境变量协议

### 4.1 优先级（高 → 低）

1. 真实环境变量
2. 仓库根 `.env` 文件
3. 字段默认值

### 4.2 命名：扁平 / 嵌套 双名等价

| 字段            | 扁平名                | 嵌套名                       |
| --------------- | --------------------- | ---------------------------- |
| `app.env`       | `APP_ENV`             | `APP__ENV`                   |
| `app.log_level` | `LOG_LEVEL`           | `APP__LOG_LEVEL`             |
| `auth.jwt_secret` | `JWT_SECRET`        | `AUTH__JWT_SECRET`           |
| `auth.jwt_alg`  | `JWT_ALG`             | `AUTH__JWT_ALG`              |
| `db.database_url` | `DATABASE_URL`      | `DB__DATABASE_URL`           |
| `redis.redis_url` | `REDIS_URL`         | `REDIS__REDIS_URL`           |
| `ollama.base_url` | `OLLAMA_BASE_URL`   | `OLLAMA__BASE_URL`           |
| `ollama.chat_model` | `OLLAMA_CHAT_MODEL` | `OLLAMA__CHAT_MODEL`       |
| `ollama.embed_model` | `OLLAMA_EMBED_MODEL` | `OLLAMA__EMBED_MODEL`    |
| `retrieval.enabled` | `RAG_ENABLED`     | `RETRIEVAL__ENABLED`         |
| `retrieval.top_k`   | `RAG_TOP_K`       | `RETRIEVAL__TOP_K`           |
| `retrieval.min_score` | `RAG_MIN_SCORE` | `RETRIEVAL__MIN_SCORE`       |
| `rate_limit.per_min`  | `RATE_LIMIT_PER_MIN` | `RATE_LIMIT__PER_MIN` |

完整映射见 `settings._FLAT_TO_NESTED`。`.env.example` 使用扁平名。

**规则**：两种命名**等价**；同时出现时**嵌套形式胜出**（与 pydantic-settings 默认一致）。

## 5. 环境差异行为

### 5.1 `APP_ENV=dev`（默认）

- `JWT_SECRET` 未配置 → `Settings.load()` 注入占位符 `dev-insecure-secret` 并写 WARNING 日志。
- 模块 `import settings` 不抛异常，首次本地启动零摩擦。

### 5.2 `APP_ENV=prod`（及其它非 dev 值）

- `JWT_SECRET` 未配置 → `ValidationError`（字段缺失）。
- `JWT_SECRET ∈ {"", "dev-insecure-secret", "change-me-in-prod"}` → `ValueError("JWT_SECRET must be explicitly configured in production.")`。

## 6. Contracts（消费方可依赖的不变量）

1. `settings` 单例在**模块导入后立即可用**，不要求显式 init 调用。
2. 字段名与字段类型在同一 minor 版本内**稳定**；新增字段走 additive change，删除或重命名字段走 BREAKING change + AGENTS.md §19 记录。
3. 运行期**不允许**修改 `settings`（pydantic 不可变）。
4. 消费方**不得**直接 `os.environ[...]` 获取已在 `settings` 声明的参数；未登记的参数先在此 capability 扩展。
5. Capability 明确**不承诺**：
   - Secret 管理（Vault / SOPS）—— 未来单独 change。
   - 运行时热重载 —— 改配置请重启进程。
   - 跨进程广播 —— 每进程独立加载。

## 7. Observability

- Dev fallback 路径写 `WARNING` 日志（logger 名 = `settings`）。
- 其它路径保持静默，避免 import-time 噪音。

## 8. Testing

契约由 `tests/unit/test_settings.py` 保证。要求覆盖：

- dev 空环境 → fallback 占位符生效。
- prod 无 / placeholder secret → raise。
- prod + 强密码 → 正常加载。
- 扁平 / 嵌套 alias 各自生效，嵌套优先。
- 默认值与 AGENTS.md §7 保持一致。
- 导出契约（`__all__`、单例、类名）。

## 9. References

- AGENTS.md §7（`.env.example` 字段清单）
- AGENTS.md §16（配置红线）
- AGENTS.md §19（v0.4 引入记录）
- 归档 change：`openspec/changes/archive/YYYY-MM-DD-bootstrap-settings-and-env/`
