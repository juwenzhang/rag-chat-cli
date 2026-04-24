# Proposal: Quality Gates + CI/CD

## Why

AGENTS.md §11/§12 明确：

> 代码风格：`ruff` + `black` + `mypy --strict`；pre-commit 钩子必备。
> 测试：pytest + pytest-asyncio + pytest-cov；**总覆盖率 ≥ 85%，`core/` ≥ 90%**。
> CI：GitHub Actions（或等价），每 PR 必跑 lint / test / coverage / docker build。

当前项目**几乎没有质量门**：
- 没有 `ruff` / `mypy` 配置。
- 没有 `pytest` 配置、没有 `conftest.py`、没有 coverage 标注。
- 没有 `.github/workflows/`。
- 没有 `pre-commit`。
- Makefile 只有 docker 命令。

前置 change 都在各自 tasks 里声明"要 `ruff check`、`mypy --strict`、`pytest -q`"。**本 change 把这些工具真正配置起来，并在 CI 中强制执行**。

## What Changes

- 新增/完善配置：
  - `pyproject.toml` 补 `[tool.ruff]` / `[tool.ruff.lint]` / `[tool.ruff.format]` / `[tool.mypy]` / `[tool.pytest.ini_options]` / `[tool.coverage.run]` / `[tool.coverage.report]`。
  - `.pre-commit-config.yaml`：ruff (lint + format) + mypy + trailing whitespace + end-of-file-fixer。
- 新增 CI workflow `.github/workflows/ci.yml`：
  - `lint`：ruff check + format check + mypy。
  - `test`：矩阵 python 3.11 / 3.12，启动 postgres + redis service container，跑 pytest。
  - `coverage`：上传到 codecov（可选），阈值门禁：总 ≥ 85%、core ≥ 90%。
  - `docker`：`docker build -f docker/api.Dockerfile` + cache。
  - `openapi-check`：`dump_openapi.py` 比对与 git 中 `docs/openapi.json` 一致。
- 新增/完善 `Makefile`：
  - `lint / lint-fix / typecheck / fmt / fmt-check / test / test-cov / openapi / openapi-check / ci`。
  - `ci` = `lint typecheck test-cov openapi-check`（本地一把梭）。
- 新增 `tests/conftest.py`（顶层）：
  - `anyio_backend = "asyncio"`。
  - `settings_override` fixture：环境变量隔离。
  - `app_client / async_engine / redis_client`（fakeredis）三件套。
- 新增 `pytest markers`：`pg`、`redis`、`slow`、`integration`，在 `pyproject.toml` 注册。
- 新增 `docs/DEVELOPMENT.md`：如何装 uv + pre-commit + 常用命令。

## Non-goals

- 不做 release 流程 / semver 自动化。
- 不做 docker 镜像推送到 registry（留给用户自己的 pipeline）。
- 不做代码扫描（Sonar / Snyk / Dependabot 可选择性手工启）。

## Impact

- **新增**：`.pre-commit-config.yaml`、`.github/workflows/ci.yml`、`tests/conftest.py`、`docs/DEVELOPMENT.md`、`scripts/dump_openapi.py`（Change 6 声明过，本 change 强制补齐）。
- **修改**：`pyproject.toml` 大量配置段、`Makefile`、`README.md`（加 badge）。
- **依赖**：dev 新增 `ruff>=0.5`、`mypy>=1.10`、`pytest-cov>=5.0`、`pre-commit>=3.7`、`types-redis`、`types-passlib`。
- **风险**：低-中。不改业务代码，但 strict mypy 可能暴露一堆已有 typing 不严谨问题。
- **回退方式**：`git revert`；本地/CI 跳过对应步骤。
