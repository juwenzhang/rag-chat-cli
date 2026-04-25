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
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[None]:
    """Remove every env var that ``settings.py`` reads, for a clean slate.

    Also ``chdir`` into an empty tmp dir so ``_parse_dotenv`` does not pick up
    the developer's real `.env` (which would smuggle a real ``JWT_SECRET`` into
    the test and make "no-secret" assertions silently pass).
    """
    for key in _MANAGED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
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


class TestDotenvFlatHoist:
    """Regression: flat aliases written in `.env` (not in os.environ) must
    still be hoisted to the right group. Without this we silently fell back
    to ``dev-insecure-secret`` even when the user had set ``JWT_SECRET=...``
    in their `.env` — and ``Settings()`` raised "auth Field required" because
    ``AuthSettings.jwt_secret`` is required and never received the value.
    """

    def test_dotenv_flat_keys_are_hoisted(
        self,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        import settings as s

        # Write a `.env` next to where settings.py looks (process cwd).
        dotenv = tmp_path / ".env"
        dotenv.write_text(
            "JWT_SECRET=from-dotenv-flat\n"
            "DATABASE_URL=sqlite+aiosqlite:///./.x.db\n"
            "OLLAMA_CHAT_MODEL=qwen-from-dotenv\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        module = importlib.reload(s)
        cfg = module.settings
        assert cfg.auth.jwt_secret == "from-dotenv-flat"
        assert cfg.db.database_url == "sqlite+aiosqlite:///./.x.db"
        assert cfg.ollama.chat_model == "qwen-from-dotenv"

    def test_os_environ_wins_over_dotenv(
        self,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        import settings as s

        (tmp_path / ".env").write_text("JWT_SECRET=from-dotenv\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("JWT_SECRET", "from-os-environ")
        module = importlib.reload(s)
        assert module.settings.auth.jwt_secret == "from-os-environ"

    def test_dotenv_strips_inline_comments_and_quotes(
        self,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        import settings as s

        (tmp_path / ".env").write_text(
            'JWT_SECRET="quoted-secret"  # inline comment\n'
            "OLLAMA_CHAT_MODEL=qwen2.5:1.5b # another\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        module = importlib.reload(s)
        cfg = module.settings
        assert cfg.auth.jwt_secret == "quoted-secret"
        assert cfg.ollama.chat_model == "qwen2.5:1.5b"

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
