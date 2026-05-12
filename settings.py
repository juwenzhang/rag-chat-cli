"""
Single source of truth for application configuration.

对齐 AGENTS.md §7：
  - 所有环境变量在此声明，其它模块禁止直接读 os.environ。
  - 本地配置来自 `.env`；生产通过真实环境变量或 secret manager 注入。
  - 支持两种命名：扁平（`.env.example` 用的 `JWT_SECRET`）与嵌套
    （pydantic-settings 默认的 `AUTH__JWT_SECRET`），二者等价；扁平形式
    通过顶层 model_validator 预先映射到嵌套结构。

Usage::

    from settings import settings
    print(settings.ollama.chat_model)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "settings"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flat → nested env var mapping
# ---------------------------------------------------------------------------
#
# pydantic-settings 的 nested delimiter（`__`）会把 env 变量切成嵌套结构，
# 但无法直接识别 `.env.example` 里的扁平名（如 `JWT_SECRET`）。因此在
# Settings 顶层做一次显式映射：扁平 env 名 → `(group, field)`。
#
# 这个表是"唯一事实来源"——新增配置时同时更新 `.env.example` 与此表。

_FLAT_TO_NESTED: dict[str, tuple[str, str]] = {
    # app
    "APP_ENV": ("app", "env"),
    "LOG_LEVEL": ("app", "log_level"),
    "REQUEST_ID_HEADER": ("app", "request_id_header"),
    "APP_HOST": ("app", "host"),
    "APP_PORT": ("app", "port"),
    "APP_CORS_ORIGINS": ("app", "cors_origins"),
    # auth
    "JWT_SECRET": ("auth", "jwt_secret"),
    "JWT_ALG": ("auth", "jwt_alg"),
    "ACCESS_TOKEN_TTL_MIN": ("auth", "access_token_ttl_min"),
    "REFRESH_TOKEN_TTL_DAY": ("auth", "refresh_token_ttl_day"),
    "AUTH_BCRYPT_ROUNDS": ("auth", "bcrypt_rounds"),
    "AUTH_REFRESH_REUSE_DETECTION": ("auth", "refresh_reuse_detection"),
    # db
    "DATABASE_URL": ("db", "database_url"),
    "DB_POOL_SIZE": ("db", "pool_size"),
    "DB_POOL_RECYCLE": ("db", "pool_recycle"),
    "DB_ECHO_SQL": ("db", "echo_sql"),
    # redis
    "REDIS_URL": ("redis", "redis_url"),
    # ollama
    "OLLAMA_BASE_URL": ("ollama", "base_url"),
    "OLLAMA_CHAT_MODEL": ("ollama", "chat_model"),
    "OLLAMA_EMBED_MODEL": ("ollama", "embed_model"),
    "OLLAMA_TIMEOUT": ("ollama", "timeout"),
    "OLLAMA_API_KEY": ("ollama", "api_key"),
    # openai (P5.1)
    "OPENAI_BASE_URL": ("openai", "base_url"),
    "OPENAI_CHAT_MODEL": ("openai", "chat_model"),
    "OPENAI_EMBED_MODEL": ("openai", "embed_model"),
    "OPENAI_API_KEY": ("openai", "api_key"),
    "OPENAI_TIMEOUT": ("openai", "timeout"),
    "OPENAI_ORGANIZATION": ("openai", "organization"),
    # retrieval
    "RAG_ENABLED": ("retrieval", "enabled"),
    "RAG_TOP_K": ("retrieval", "top_k"),
    "RAG_MIN_SCORE": ("retrieval", "min_score"),
    "RAG_EMBED_DIM": ("retrieval", "embed_dim"),
    # rate limit
    "RATE_LIMIT_PER_MIN": ("rate_limit", "per_min"),
    # security (Sprint 2): Fernet key for at-rest encryption of provider API keys.
    "PROVIDER_ENCRYPTION_KEY": ("security", "provider_encryption_key"),
}


# ---------------------------------------------------------------------------
# Grouped models
# ---------------------------------------------------------------------------


class _GroupBase(BaseModel):
    """分组基类：忽略未知字段。"""

    model_config = ConfigDict(extra="ignore")


class AppSettings(_GroupBase):
    env: Literal["dev", "prod"] = "dev"
    log_level: str = "INFO"
    request_id_header: str = "X-Request-ID"
    # HTTP surface (P6 add-fastapi-rest-api).
    host: str = "0.0.0.0"  # noqa: S104 — dev convenience; prod usually reverse-proxied
    port: int = 8000
    # CSV env var `APP_CORS_ORIGINS=http://a,http://b` becomes `["http://a", "http://b"]`.
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


class AuthSettings(_GroupBase):
    jwt_secret: str
    jwt_alg: str = "HS256"
    access_token_ttl_min: int = 15
    refresh_token_ttl_day: int = 7
    # bcrypt rounds — 12 is a sensible default for 2026-era hardware. See
    # AGENTS.md §6 and openspec/changes/add-jwt-auth/design.md.
    bcrypt_rounds: int = 12
    # When True, detecting a re-used (already revoked) refresh token triggers
    # mass-revocation of every live refresh token for that user. AGENTS.md §6.
    refresh_reuse_detection: bool = True


class DBSettings(_GroupBase):
    database_url: str = "postgresql+asyncpg://rag:rag@postgres:5432/ragdb"
    # Async engine pool knobs (see AGENTS.md §4 / docs/DEVELOPMENT.md).
    pool_size: int = 10
    pool_recycle: int = 1800  # seconds; recycle connections older than this.
    echo_sql: bool = False


class RedisSettings(_GroupBase):
    redis_url: str = "redis://redis:6379/0"


class OllamaSettings(_GroupBase):
    base_url: str = "http://ollama:11434"
    chat_model: str = "qwen2.5:1.5b"
    embed_model: str = "nomic-embed-text"
    timeout: int = 120
    # Bearer token for hosted/proxied Ollama (e.g. ollama.com cloud,
    # or a self-hosted reverse proxy that gates `/api/*`).
    # Sent as `Authorization: Bearer <api_key>` on every request when set.
    # Local default `http://localhost:11434` does not require this.
    api_key: str | None = None


class OpenAISettings(_GroupBase):
    """OpenAI-compatible endpoint (#20 P5.1).

    Works against api.openai.com and any compatible server (vLLM, LM Studio,
    Together, Groq, …). Override ``base_url`` to point at a local /
    self-hosted endpoint; default points at OpenAI proper.
    """

    base_url: str = "https://api.openai.com/v1"
    chat_model: str = "gpt-4o-mini"
    embed_model: str = "text-embedding-3-small"
    api_key: str | None = None
    timeout: int = 120
    organization: str | None = None


class RetrievalSettings(_GroupBase):
    enabled: bool = True
    top_k: int = 4
    min_score: float = 0.25
    # Embedding dimension used by pgvector `Vector(dim)` column.
    # Defaults to 768 for `nomic-embed-text`; switch with the model.
    embed_dim: int = 768


class RateLimitSettings(_GroupBase):
    per_min: int = 60


class SecuritySettings(_GroupBase):
    """At-rest secret material (Sprint 2 — provider API keys).

    ``provider_encryption_key`` is a base64 urlsafe Fernet key (44 chars).
    Generate one with ``cryptography.fernet.Fernet.generate_key()``.

    ``None`` in ``env=dev`` falls back to a deterministic dev key with a
    loud warning — convenient for first-run local dev, **never** safe in
    prod. ``env=prod`` requires an explicit key.
    """

    provider_encryption_key: str | None = None


# ---------------------------------------------------------------------------
# Top-level Settings
# ---------------------------------------------------------------------------


_DEV_INSECURE_SECRET = "dev-insecure-secret"  # noqa: S105 — 显式占位符
_PLACEHOLDER_SECRETS = frozenset({_DEV_INSECURE_SECRET, "change-me-in-prod", ""})


def _parse_dotenv(path: str = ".env") -> dict[str, str]:
    """Best-effort `.env` parser (no quoting / interpolation tricks).

    pydantic-settings reads `.env` itself, but it does so AFTER our
    ``model_validator(mode="before")`` runs — which means flat aliases like
    ``JWT_SECRET`` written in `.env` are invisible to
    :func:`_collect_flat_env_overrides`. Re-parsing here closes that gap.

    Lines starting with ``#`` and blank lines are skipped; trailing inline
    comments after `` # `` are stripped. Quotes around values are removed.
    """
    try:
        raw = open(path, encoding="utf-8").read()  # noqa: SIM115 — small file, explicit close not needed
    except OSError:
        return {}
    out: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip optional inline `# comment`. Only when the `#` is preceded by
        # whitespace, so `password=#1abc` (legit value with leading hash) survives.
        if " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        # Strip matching surrounding quotes.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def _collect_flat_env_overrides() -> dict[str, dict[str, str]]:
    """把扁平命名（`JWT_SECRET`）合并成 ``{group: {field: value}}``。

    优先级：真实 ``os.environ`` > `.env` 文件 —— 与 pydantic-settings 自身
    对嵌套名的优先级保持一致。
    """
    dotenv = _parse_dotenv()
    nested: dict[str, dict[str, str]] = {}
    for flat_key, (group, field) in _FLAT_TO_NESTED.items():
        if flat_key in os.environ:
            value = os.environ[flat_key]
        elif flat_key in dotenv:
            value = dotenv[flat_key]
        else:
            continue
        nested.setdefault(group, {})[field] = value
    return nested


class Settings(BaseSettings):
    """应用级配置根对象。

    读取优先级（高→低）：真实环境变量 > `.env` 文件 > 字段默认值。

    - `env=dev` 且未提供 `JWT_SECRET` 时使用不安全占位符并 `logger.warning`。
    - `env=prod` 时必须显式配置非占位符的 `JWT_SECRET`，否则 `ValueError`。
    """

    app: AppSettings = Field(default_factory=AppSettings)
    auth: AuthSettings
    db: DBSettings = Field(default_factory=DBSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # Flat alias hoisting (BEFORE validation)
    # ------------------------------------------------------------------
    @model_validator(mode="before")
    @classmethod
    def _hoist_flat_env(cls, data: Any) -> Any:
        """把扁平环境变量（如 JWT_SECRET）合并到对应的嵌套分组。

        已存在的嵌套值（`AUTH__JWT_SECRET`）拥有更高优先级，不会被扁平值覆盖。
        """
        if not isinstance(data, dict):
            return data
        flat = _collect_flat_env_overrides()
        for group, fields in flat.items():
            existing = data.get(group)
            if isinstance(existing, dict):
                for field, value in fields.items():
                    existing.setdefault(field, value)
            else:
                data[group] = fields
        return data

    # ------------------------------------------------------------------
    # Factory with dev fallback
    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> Settings:
        """带 dev 回退的构造函数。

        `APP_ENV=dev` 且未配置 JWT_SECRET 时，注入不安全占位符并警告，
        保证首次本地启动不因缺配置而失败；`prod` 环境则必须显式配置。
        """
        try:
            return cls()
        except Exception:
            # 检查当前 env；优先看显式 env var，再看 .env 通过 AppSettings 默认解析
            env_name = os.environ.get("APP_ENV") or os.environ.get("APP__ENV")
            if env_name is None:
                env_name = AppSettings().env  # 默认 "dev"
            if env_name != "dev":
                raise
            logger.warning(
                "JWT_SECRET not set; falling back to insecure dev secret. "
                "DO NOT use this in production."
            )
            return cls(auth=AuthSettings(jwt_secret=_DEV_INSECURE_SECRET))

    @field_validator("auth")
    @classmethod
    def _check_prod_secret(cls, v: AuthSettings, info: Any) -> AuthSettings:
        """生产环境禁止使用不安全占位符。"""
        app_cfg: AppSettings = info.data.get("app") or AppSettings()  # type: ignore[call-arg]
        if app_cfg.env == "prod" and v.jwt_secret in _PLACEHOLDER_SECRETS:
            raise ValueError("JWT_SECRET must be explicitly configured in production.")
        return v


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

settings = Settings.load()
