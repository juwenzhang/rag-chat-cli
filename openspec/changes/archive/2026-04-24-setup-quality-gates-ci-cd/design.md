# Design: Quality Gates + CI/CD

## Context

AGENTS.md §11 / §12 的约束 + §18 pre-PR 清单（lint / typecheck / test / coverage / openapi / compose build 全绿）。所有前面 10 个 change 都把"质量门"作为验收条件，本 change 把这些门**自动化**。

## Goals / Non-Goals

**Goals**
- **一键本地验证**：`make ci` 跑完全部门（与 PR CI 等价）。
- **PR 不过门即不可合并**：CI 必须 red 就阻止 merge。
- **分层覆盖率门**：`core/` 90%，其它 85%（符合 §12）。
- **稳定 matrix**：Python 3.11 与 3.12 都绿。
- **OpenAPI 不漂移**：`docs/openapi.json` 与代码定义一致。

**Non-Goals**
- 不做性能基准测试（`pytest-benchmark` 可后续）。
- 不做 mutation testing。

## Architecture / Config

### `pyproject.toml` 片段

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
src = ["."]
extend-exclude = ["alembic/versions", "web"]

[tool.ruff.lint]
select = [
  "E", "W", "F",        # pycodestyle + pyflakes
  "I",                  # isort
  "B",                  # bugbear
  "UP",                 # pyupgrade
  "SIM",                # simplify
  "RUF",                # ruff-specific
  "ASYNC",              # async-specific
  "S",                  # bandit-lite
  "T20",                # no print
]
ignore = [
  "S101",               # assert 在测试中需要
  "E501",               # 由 formatter 处理
]
per-file-ignores = { "tests/**" = ["S", "T20"] }

[tool.ruff.format]
quote-style = "double"
line-ending = "lf"

[tool.mypy]
python_version = "3.11"
strict = true
warn_unused_ignores = true
warn_return_any = true
ignore_missing_imports = false
plugins = ["pydantic.mypy"]
exclude = ["alembic/versions/", "web/"]
# 逐步严格：一些第三方暂无 stubs
[[tool.mypy.overrides]]
module = ["passlib.*", "jose.*", "arq.*", "pgvector.*", "respx.*", "fakeredis.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
minversion = "8.0"
addopts = ["-ra", "--strict-markers", "--strict-config"]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
  "pg: requires PostgreSQL docker container",
  "redis: requires Redis docker container",
  "slow: slow tests (> 1s)",
  "integration: cross-module integration tests",
]

[tool.coverage.run]
branch = true
source = ["api", "app", "core", "db", "workers", "settings"]
omit = ["alembic/*", "scripts/*", "tests/*", "*/__init__.py"]

[tool.coverage.report]
precision = 1
show_missing = true
skip_covered = false
fail_under = 85
exclude_lines = [
  "pragma: no cover",
  "raise NotImplementedError",
  "if TYPE_CHECKING:",
  "if __name__ == .__main__.:",
]
```

分层阈值用 `scripts/check_coverage.py` 二次校验：

```python
# 从 .coverage 读取按文件覆盖率；按前缀 `core/` 聚合；断言 >= 90。
```

### `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.5
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-merge-conflict
      - id: mixed-line-ending

  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: uv run mypy
        language: system
        pass_filenames: false
        args: [".", "--exclude", "alembic/versions"]
        types_or: [python]
```

### `Makefile`

```make
.PHONY: help lint lint-fix fmt fmt-check typecheck test test-cov test-fast openapi openapi-check ci up down logs rebuild ps

help:
	@awk -F':' '/^[a-zA-Z_-]+:/ && $$1!~/PHONY/ {print "  \033[36m"$$1"\033[0m"}' $(MAKEFILE_LIST)

lint:        ; uv run ruff check .
lint-fix:    ; uv run ruff check . --fix
fmt:         ; uv run ruff format .
fmt-check:   ; uv run ruff format --check .
typecheck:   ; uv run mypy .
test:        ; uv run pytest -q
test-fast:   ; uv run pytest -q -m "not pg and not redis and not slow"
test-cov:    ; uv run pytest --cov --cov-report=term-missing --cov-report=xml && uv run python scripts/check_coverage.py
openapi:     ; uv run python scripts/dump_openapi.py > docs/openapi.json
openapi-check: ; uv run python scripts/dump_openapi.py | diff -u docs/openapi.json -
ci: lint fmt-check typecheck test-cov openapi-check

up:          ; docker compose --profile web up -d
down:        ; docker compose down
logs:        ; docker compose logs -f --tail=100
rebuild:     ; docker compose build --no-cache
ps:          ; docker compose ps
```

### `.github/workflows/ci.yml`

```yaml
name: ci
on:
  push: { branches: [main] }
  pull_request:

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install 3.11
      - run: uv sync --frozen
      - run: uv run ruff check .
      - run: uv run ruff format --check .

  typecheck:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen
      - run: uv run mypy .

  test:
    runs-on: ubuntu-latest
    needs: lint
    strategy:
      fail-fast: false
      matrix: { python: ["3.11", "3.12"] }
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env: { POSTGRES_USER: rag, POSTGRES_PASSWORD: rag, POSTGRES_DB: ragdb }
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U rag"
          --health-interval 5s --health-timeout 3s --health-retries 10
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
        options: --health-cmd "redis-cli ping" --health-interval 5s --health-retries 10
    env:
      APP__ENV: dev
      AUTH__JWT_SECRET: ci-secret-not-for-prod-xxxxxxxxxxxxxxxxxxxx
      DB__DATABASE_URL: postgresql+asyncpg://rag:rag@localhost:5432/ragdb
      REDIS__URL: redis://localhost:6379/0
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install ${{ matrix.python }}
      - run: uv sync --frozen
      - run: uv run alembic upgrade head
      - run: uv run pytest --cov --cov-report=xml
      - run: uv run python scripts/check_coverage.py
      - uses: codecov/codecov-action@v4
        if: matrix.python == '3.11'
        with: { files: ./coverage.xml, fail_ci_if_error: false }

  docker-build:
    runs-on: ubuntu-latest
    needs: [lint, typecheck]
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v6
        with:
          context: .
          file: docker/api.Dockerfile
          push: false
          cache-from: type=gha
          cache-to: type=gha,mode=max
          tags: ragchat-api:ci

  openapi-check:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --frozen
      - run: |
          uv run python scripts/dump_openapi.py > /tmp/openapi.json
          diff -u docs/openapi.json /tmp/openapi.json
```

### `tests/conftest.py`

```python
@pytest.fixture(scope="session")
def anyio_backend() -> str: return "asyncio"

@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    for k in ("DB__DATABASE_URL", "REDIS__URL", "AUTH__JWT_SECRET"): ...
    # 默认注入 sqlite + fakeredis + 测试 secret

@pytest_asyncio.fixture
async def async_engine() -> AsyncIterator[AsyncEngine]:
    # sqlite in-memory + 程序化 alembic upgrade head（支持的表）

@pytest_asyncio.fixture
async def app_client(async_engine) -> AsyncIterator[AsyncClient]:
    from api.app import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
```

### `scripts/check_coverage.py`

```python
# 读 coverage.xml → 聚合 core/* 覆盖率；断言 >= 90；否则 sys.exit(1)。
```

### `scripts/dump_openapi.py`

```python
from api.app import create_app
import json, sys
app = create_app()
json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
```

## Alternatives Considered

- **black 代替 ruff format**：ruff format 对齐 black 且更快，统一工具链。
- **tox 多环境**：uv + matrix 已够。
- **pre-commit.ci**：依赖外部服务；本地 + GH Actions 足够。

## Risks & Mitigations

- **风险**：mypy strict 一开启报大量旧错。
  **缓解**：按目录分阶段 strict：先 `core/ api/` strict，其它 `no-strict`；通过 `[[overrides]]` 配置；后续 change 逐步收紧。
  本 change 先以 `core api db workers` 为 strict 范围，`app utils scripts alembic` 放宽。
- **风险**：CI 无 Ollama 导致 RAG 测试失败。
  **缓解**：所有 Ollama 调用在测试中都 `respx.mock`，不连真 Ollama。
- **风险**：coverage 阈值过严阻塞开发。
  **缓解**：PR 级别 soft fail（warning），main 分支 hard fail（需要配置 branch protection）；先 hard 推，出问题降为 soft。

## Testing Strategy

- 元测试：
  - 故意引入一条未使用 import，确保 `ruff` 捕获。
  - 故意在 `core/` 写一条无类型注解函数，确保 `mypy --strict` 报错。
  - 故意删一条测试让覆盖率掉到 84%，CI 红。
- 本地验证：
  - `pre-commit install && pre-commit run --all-files` 全绿。
  - `make ci` 全绿。
