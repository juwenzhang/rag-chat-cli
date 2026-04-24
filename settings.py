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
    # auth
    "JWT_SECRET": ("auth", "jwt_secret"),
    "JWT_ALG": ("auth", "jwt_alg"),
    "ACCESS_TOKEN_TTL_MIN": ("auth", "access_token_ttl_min"),
    "REFRESH_TOKEN_TTL_DAY": ("auth", "refresh_token_ttl_day"),
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
    # retrieval
    "RAG_ENABLED": ("retrieval", "enabled"),
    "RAG_TOP_K": ("retrieval", "top_k"),
    "RAG_MIN_SCORE": ("retrieval", "min_score"),
    "RAG_EMBED_DIM": ("retrieval", "embed_dim"),
    # rate limit
    "RATE_LIMIT_PER_MIN": ("rate_limit", "per_min"),
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


class AuthSettings(_GroupBase):
    jwt_secret: str
    jwt_alg: str = "HS256"
    access_token_ttl_min: int = 15
    refresh_token_ttl_day: int = 7


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


class RetrievalSettings(_GroupBase):
    enabled: bool = True
    top_k: int = 4
    min_score: float = 0.25
    # Embedding dimension used by pgvector `Vector(dim)` column.
    # Defaults to 768 for `nomic-embed-text`; switch with the model.
    embed_dim: int = 768


class RateLimitSettings(_GroupBase):
    per_min: int = 60


# ---------------------------------------------------------------------------
# Top-level Settings
# ---------------------------------------------------------------------------


_DEV_INSECURE_SECRET = "dev-insecure-secret"  # noqa: S105 — 显式占位符
_PLACEHOLDER_SECRETS = frozenset({_DEV_INSECURE_SECRET, "change-me-in-prod", ""})


def _collect_flat_env_overrides() -> dict[str, dict[str, str]]:
    """扫描环境变量，把扁平名映射成 {group: {field: value}}。"""
    nested: dict[str, dict[str, str]] = {}
    for flat_key, (group, field) in _FLAT_TO_NESTED.items():
        if flat_key in os.environ:
            nested.setdefault(group, {})[field] = os.environ[flat_key]
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
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)

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
