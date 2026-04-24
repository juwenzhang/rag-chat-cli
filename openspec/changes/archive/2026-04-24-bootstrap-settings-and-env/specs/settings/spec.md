# Settings Capability — Delta Spec

> **Change**: `bootstrap-settings-and-env`
> **Capability**: `settings`
> **Status**: Additive (新增能力，无现存 spec 要修改)

## 1. 概述

本 change 引入 **`settings` capability**：仓库的唯一**应用级配置入口**。

- 所有运行时可配参数（env/auth/db/redis/ollama/retrieval/rate_limit）在此声明并类型化。
- 其它模块**禁止**直接读 `os.environ` 或读写项目里的配置文件（AGENTS.md §7 / §16 硬约束）。
- 本地开发通过 `.env` 覆盖；生产通过真实环境变量或 secret manager 注入。

## 2. 新增行为（ADDED）

### 2.1 顶层 API

- 模块 `settings`（仓库根 `settings.py`）导出：
  - `settings`：module-level 单例，类型为 `Settings`（`pydantic_settings.BaseSettings` 子类）。
  - `Settings`：配置类本身；暴露 `classmethod load() -> Settings` 作为带 dev-fallback 的构造入口。
  - `__all__ = ["settings", "Settings"]`。

- 使用方式（规范）：

  ```python
  from settings import settings

  base_url = settings.ollama.base_url
  jwt_secret = settings.auth.jwt_secret
  ```

### 2.2 分组结构

七个分组（均为 `pydantic.BaseModel` 子类），每个分组的字段、默认值、类型与 AGENTS.md §7 一致：

| 分组         | 必填字段        | 默认值示例                                                    |
| ------------ | --------------- | ------------------------------------------------------------- |
| `app`        | —               | `env="dev"`, `log_level="INFO"`, `request_id_header="X-Request-ID"` |
| `auth`       | `jwt_secret`    | `jwt_alg="HS256"`, `access_token_ttl_min=15`, `refresh_token_ttl_day=7` |
| `db`         | —               | `database_url="postgresql+asyncpg://rag:rag@postgres:5432/ragdb"` |
| `redis`      | —               | `redis_url="redis://redis:6379/0"`                            |
| `ollama`     | —               | `base_url="http://ollama:11434"`, `chat_model="qwen2.5:1.5b"`, `embed_model="nomic-embed-text"`, `timeout=120` |
| `retrieval`  | —               | `enabled=True`, `top_k=4`, `min_score=0.25`                   |
| `rate_limit` | —               | `per_min=60`                                                  |

### 2.3 环境变量命名（双名兼容）

读取优先级（高 → 低）：**真实环境变量 > `.env` 文件 > 字段默认值**。

每个字段支持两种等价命名：

- **扁平形式**（`.env.example` 使用）：`JWT_SECRET` / `DATABASE_URL` / `REDIS_URL` / `OLLAMA_BASE_URL` / `OLLAMA_CHAT_MODEL` / `RAG_TOP_K` / `RATE_LIMIT_PER_MIN` / …
- **嵌套形式**（pydantic-settings 原生）：`AUTH__JWT_SECRET` / `DB__DATABASE_URL` / `REDIS__REDIS_URL` / `OLLAMA__BASE_URL` / `RETRIEVAL__TOP_K` / `RATE_LIMIT__PER_MIN` / …

**规则**：

- 两种形式**等价**，任一生效即可。
- 若二者同时出现，**嵌套形式胜出**（与 pydantic-settings 默认一致）。
- 完整的扁平名与嵌套名对应关系由 `settings._FLAT_TO_NESTED` 维护，并与 `.env.example` 保持一对一同步。

### 2.4 环境特异行为

- **`APP_ENV=dev` 且未配置 `JWT_SECRET`**：
  `Settings.load()` 自动注入占位符 `dev-insecure-secret`，并通过 `logger.warning(...)` 发出提醒；模块导入不报错。
- **`APP_ENV=prod`（或任意非 `dev`）**：
  - 若 `JWT_SECRET` 未配置 → `ValidationError`（字段缺失）。
  - 若 `JWT_SECRET` 等于占位符集合之一（`""`, `dev-insecure-secret`, `change-me-in-prod`）→ `ValueError("JWT_SECRET must be explicitly configured in production.")`。

### 2.5 加载策略

- `Settings()` 构造 = 纯 pydantic-settings 行为（env + `.env`）。
- `Settings.load()` 构造 = 在纯构造失败时，若当前 env 为 `dev` 则补占位符重试；否则重新抛出原异常。
- 模块顶层执行 `settings = Settings.load()`，因此首次 `import settings` 即可拿到单例。

## 3. 不变量 / Contracts

消费方（所有其它模块 / change）**可以依赖**以下不变量：

1. `settings` 单例在模块导入后**立即**可用，不要求显式初始化调用。
2. `settings.<group>.<field>` 的字段名与类型在 minor 版本内稳定；新增字段走 additive change，删除字段走 BREAKING change + AGENTS.md §19 记录。
3. 消费方**不得**在运行时修改 `settings` 的字段（pydantic 默认不可变保护）。
4. 消费方**不得**自行读取 `os.environ` 获取已在 `settings` 声明的参数；如需未登记的参数，先向 `settings` 追加分组/字段。
5. 本 capability **不承诺**：
   - Secret 管理（Vault / SOPS）——未来在独立 change 引入。
   - 运行时热重载（reload on SIGHUP 等）——当前无此需求，走重启流程。
   - 跨进程配置广播——每个进程启动各自加载。

## 4. 可观测性

- dev-fallback 路径写 WARNING 级日志到 `settings` 模块 logger。
- 其它路径不产生日志，避免在 import-time 产生噪音。

## 5. 测试契约

`tests/unit/test_settings.py` 覆盖：

- dev 空环境 → fallback 占位符生效。
- prod 无 secret / placeholder secret → raise。
- prod + 强密码 → 正常加载。
- 扁平 alias / 嵌套 alias 各自生效，且嵌套优先。
- 导出契约：`__all__`、`settings` / `Settings` 可访问。
- 默认值与 AGENTS.md §7 一致（chat_model、embed_model、top_k、min_score、rate_limit 等）。
