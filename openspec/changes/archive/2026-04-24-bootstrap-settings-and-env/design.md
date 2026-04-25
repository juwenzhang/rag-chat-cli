# Design: Bootstrap Settings & Env

## Context

AGENTS.md §7 要求：

> 单一配置入口 `settings.py`（`pydantic-settings`）。所有环境变量在此声明，其它模块**禁止直接读 `os.environ`**。

当前仓库中 `utils/config.py` 读取 `config.json`，`main.py` 直接读 `os.environ`，后续引入 DB/Redis/JWT 时会进一步扩散。必须先立一个"单源头"的 settings 层。

## Goals / Non-Goals

**Goals**
- 提供强类型、层级清晰、可 `.env` 覆盖的 `settings` 单例。
- 覆盖 AGENTS.md §7 `.env.example` 列出的所有字段（app / auth / db / redis / ollama / retrieval / rate limit）。
- 与 `config.json` 双向共存一个阶段，提供一次性迁移函数。

**Non-Goals**
- 不在本次引入 `DATABASE_URL` 的实际连接逻辑。
- 不做 secret 管理（Vault/SOPS），仅靠 `.env`。

## Architecture

```
┌─────────────────┐        reads        ┌───────────────┐
│ settings.py     │ ───────────────────▶ │  .env         │
│ (pydantic-      │                      └───────────────┘
│  settings)      │        reads-legacy  ┌───────────────┐
│                 │ ───────────────────▶ │  config.json  │ (deprecated shim)
└─────────────────┘                      └───────────────┘
        │
        ▼
  from settings import settings   ← 所有新代码的唯一入口
```

### 分组 Models

```python
class AppSettings(BaseModel):
    env: Literal["dev", "prod"] = "dev"
    log_level: str = "INFO"
    request_id_header: str = "X-Request-ID"

class AuthSettings(BaseModel):
    jwt_secret: str
    jwt_alg: str = "HS256"
    access_token_ttl_min: int = 15
    refresh_token_ttl_day: int = 7

class DBSettings(BaseModel):
    database_url: str = "postgresql+asyncpg://rag:rag@postgres:5432/ragdb"

class RedisSettings(BaseModel):
    redis_url: str = "redis://redis:6379/0"

class OllamaSettings(BaseModel):
    base_url: str = "http://ollama:11434"
    chat_model: str = "qwen2.5:1.5b"
    embed_model: str = "nomic-embed-text"
    timeout: int = 120

class RetrievalSettings(BaseModel):
    enabled: bool = True
    top_k: int = 4
    min_score: float = 0.25

class RateLimitSettings(BaseModel):
    per_min: int = 60

class Settings(BaseSettings):
    app: AppSettings = Field(default_factory=AppSettings)
    auth: AuthSettings
    db: DBSettings = Field(default_factory=DBSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

settings = Settings()  # module-level singleton
```

### 环境变量命名

采用嵌套 delimiter `__`，示例：
- `AUTH__JWT_SECRET=xxx`
- `DB__DATABASE_URL=postgresql+asyncpg://...`
- `OLLAMA__CHAT_MODEL=qwen2.5:1.5b`

这样既保留 AGENTS.md §7 示例中的扁平风格（`.env.example` 里写的是 `JWT_SECRET`、`DATABASE_URL`），也能映射到嵌套结构——通过 `AliasChoices` 双名兼容：

```python
jwt_secret: str = Field(validation_alias=AliasChoices("AUTH__JWT_SECRET", "JWT_SECRET"))
```

### Legacy 适配

```python
def load_legacy_config() -> dict:
    """Read ./config.json for backward compat; deprecated."""
    path = Path("config.json")
    if not path.exists():
        return {}
    import json, warnings
    warnings.warn("config.json is deprecated, migrate to .env / settings.py", DeprecationWarning)
    return json.loads(path.read_text())
```

调用方只在 `app/cli.py` 启动时 `merge` 一次，**不**在 `settings` 内部做魔法。

## Alternatives Considered

- **dynaconf / hydra**：比 pydantic-settings 重，AGENTS.md §1 已明确 pydantic 技术栈，保持一致性。
- **纯 `os.getenv` + 模块常量**：被 AGENTS.md §16 明确禁止，不予考虑。

## Risks & Mitigations

- **风险**：启动期 `JWT_SECRET` 未配置直接报错，影响本地首次体验。
  **缓解**：`.env.example` 给 `change-me-in-prod` 占位；`settings.py` 在 `env=dev` 时允许使用 insecure 默认并 `logger.warning`。
- **风险**：`__` 分隔符与老 `.env` 变量冲突。
  **缓解**：用 `AliasChoices` 双名。

## Testing Strategy

- 单元测试：`tests/unit/test_settings.py`
  - 空环境下加载默认值（dev 模式允许默认 secret）。
  - `env=prod` 且无 `JWT_SECRET` 时应 raise `ValidationError`。
  - 同时支持 `JWT_SECRET` 与 `AUTH__JWT_SECRET`。
  - `load_legacy_config()` 能读取临时 `config.json` 并发出 `DeprecationWarning`。
