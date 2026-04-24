"""Unit tests for settings.py (pydantic-settings entry point)."""

from __future__ import annotations

import importlib
from collections.abc import Iterator

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_MANAGED_ENV_KEYS = (
    "APP_ENV",
    "APP__ENV",
    "LOG_LEVEL",
    "APP__LOG_LEVEL",
    "JWT_SECRET",
    "AUTH__JWT_SECRET",
    "JWT_ALG",
    "AUTH__JWT_ALG",
    "DATABASE_URL",
    "DB__DATABASE_URL",
    "REDIS_URL",
    "REDIS__REDIS_URL",
    "OLLAMA_BASE_URL",
    "OLLAMA__BASE_URL",
    "OLLAMA_CHAT_MODEL",
    "OLLAMA__CHAT_MODEL",
    "OLLAMA_EMBED_MODEL",
    "OLLAMA__EMBED_MODEL",
    "OLLAMA_TIMEOUT",
    "OLLAMA__TIMEOUT",
    "RAG_ENABLED",
    "RETRIEVAL__ENABLED",
    "RAG_TOP_K",
    "RETRIEVAL__TOP_K",
    "RAG_MIN_SCORE",
    "RETRIEVAL__MIN_SCORE",
    "RATE_LIMIT_PER_MIN",
    "RATE_LIMIT__PER_MIN",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove every env var that ``settings.py`` reads, for a clean slate."""
    for key in _MANAGED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture
def settings_module(clean_env: None):
    """Reload the ``settings`` module under the cleaned environment.

    Each test gets a fresh singleton (avoid caching across tests).
    """
    import settings as s

    return importlib.reload(s)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDevFallback:
    """`env=dev` 时无 JWT_SECRET 应自动 fallback 到不安全占位符。"""

    def test_default_uses_insecure_dev_secret(
        self, settings_module, caplog: pytest.LogCaptureFixture
    ) -> None:
        # 模块导入时就会调用 Settings.load()；singleton 必须已存在
        assert settings_module.settings.app.env == "dev"
        assert settings_module.settings.auth.jwt_secret == "dev-insecure-secret"

    def test_defaults_match_agents_md_section_7(self, settings_module) -> None:
        cfg = settings_module.settings
        assert cfg.ollama.chat_model == "qwen2.5:1.5b"
        assert cfg.ollama.embed_model == "nomic-embed-text"
        assert cfg.retrieval.top_k == 4
        assert cfg.retrieval.min_score == pytest.approx(0.25)
        assert cfg.rate_limit.per_min == 60


class TestProdStrict:
    """`env=prod` 时必须显式配置 JWT_SECRET，占位符不可接受。"""

    def test_prod_without_secret_raises(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import settings as s

        monkeypatch.setenv("APP_ENV", "prod")
        with pytest.raises(Exception):
            importlib.reload(s)

    def test_prod_with_placeholder_raises(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import settings as s

        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("JWT_SECRET", "change-me-in-prod")
        with pytest.raises(Exception):
            importlib.reload(s)

    def test_prod_with_real_secret_passes(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import settings as s

        monkeypatch.setenv("APP_ENV", "prod")
        monkeypatch.setenv("JWT_SECRET", "super-strong-production-secret")
        module = importlib.reload(s)
        assert module.settings.app.env == "prod"
        assert module.settings.auth.jwt_secret == "super-strong-production-secret"


class TestFlatAndNestedAliasesEquivalent:
    """扁平（`JWT_SECRET`）与嵌套（`AUTH__JWT_SECRET`）应等价。"""

    def test_flat_alias_applies(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        import settings as s

        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.setenv("JWT_SECRET", "flat-secret")
        monkeypatch.setenv("OLLAMA_CHAT_MODEL", "llama3.2")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:y@h/d")
        module = importlib.reload(s)
        cfg = module.settings
        assert cfg.auth.jwt_secret == "flat-secret"
        assert cfg.ollama.chat_model == "llama3.2"
        assert cfg.db.database_url == "postgresql+asyncpg://x:y@h/d"

    def test_nested_alias_applies(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        import settings as s

        monkeypatch.setenv("APP__ENV", "dev")
        monkeypatch.setenv("AUTH__JWT_SECRET", "nested-secret")
        monkeypatch.setenv("OLLAMA__CHAT_MODEL", "llama3.3")
        module = importlib.reload(s)
        cfg = module.settings
        assert cfg.auth.jwt_secret == "nested-secret"
        assert cfg.ollama.chat_model == "llama3.3"

    def test_nested_wins_over_flat_when_both_present(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """若扁平与嵌套同时存在，嵌套形式应胜出（与 pydantic-settings 默认一致）。"""
        import settings as s

        monkeypatch.setenv("APP_ENV", "dev")
        monkeypatch.setenv("AUTH__JWT_SECRET", "nested-win")
        monkeypatch.setenv("JWT_SECRET", "flat-lose")
        module = importlib.reload(s)
        assert module.settings.auth.jwt_secret == "nested-win"


class TestPublicAPI:
    """模块的导出契约。"""

    def test_all_exports(self, settings_module) -> None:
        assert hasattr(settings_module, "settings")
        assert hasattr(settings_module, "Settings")
        assert set(settings_module.__all__) == {"settings", "Settings"}
