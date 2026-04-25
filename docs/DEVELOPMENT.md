# Development Guide

> Companion to `AGENTS.md` — `AGENTS.md` states the **rules**,
> this doc states the **workflows**.

## Prerequisites

- **Python**: 3.10 is the current pinned version (`.python-version`).
  CI also verifies 3.11.
- **uv**: [`astral-sh/uv`](https://github.com/astral-sh/uv) 0.5+ —
  the only Python package/runtime manager this repo uses.
- **Docker** (optional, future): used once P4+ changes land the
  Postgres / Redis service containers.

## First-time setup

```bash
# 1. Clone & enter repo
git clone git@github.com:juwenzhang/rag-chat-cli.git
cd rag-chat-cli

# 2. Install the dev toolchain (ruff + mypy + pytest-cov + pre-commit + pytest)
uv sync --extra dev

# 3. Create .env (safe defaults, dev-only placeholder secret)
make env

# 4. Install git hooks
uv run pre-commit install
```

`make env` copies `.env.example` → `.env` unless one already exists.

## Daily workflow

| Task                      | Command              | Notes                                         |
|---------------------------|----------------------|-----------------------------------------------|
| Run interactive CLI       | `make dev.cli`       | Boots `python main.py chat`                   |
| Lint                      | `make lint`          | Ruff, read-only                               |
| Auto-fix lint             | `make lint-fix`      | Ruff + auto-fix                               |
| Format (write)            | `make fmt`           | Ruff format                                   |
| Format check              | `make fmt-check`     | Used by CI                                    |
| Type-check                | `make typecheck`     | `uvx mypy --strict`                           |
| Run tests                 | `make test`          | All tests                                     |
| Fast tests                | `make test-fast`     | Skips slow / pg / redis / integration markers |
| Coverage (soft)           | `make test-cov`      | Reports only                                  |
| Coverage (strict)         | `make test-cov-strict` | Fails if below AGENTS.md §12 thresholds     |
| **Full CI simulation**    | `make ci`            | `lint + fmt-check + typecheck + test`         |

`make help` prints all targets.

## Pre-commit

The configured hooks are intentionally light (ruff + basic hygiene, **no mypy**
because it is too slow for per-commit). Run the full type-check locally via
`make typecheck` or rely on the CI job `typecheck`.

```bash
# Run all hooks against the whole repo once (good after a rebase):
uv run pre-commit run --all-files
```

## Coverage thresholds

AGENTS.md §12 targets are total ≥ 85 % and `core/` ≥ 90 %.
Current baseline (P3 landing point) sits below both; gating is therefore
**soft** by default. Overrides:

```bash
# Bump expectations temporarily (useful in PRs that add tests):
COV_TOTAL_MIN=70 COV_CORE_MIN=80 make test-cov-strict
```

`scripts/check_coverage.py` is stdlib-only — it runs even outside the dev venv.

## Adding a test marker

1. Edit `[tool.pytest.ini_options].markers` in `pyproject.toml`.
2. Document the intent in one line ("requires X", "slow", …).
3. Reference it via `@pytest.mark.<name>` on affected tests.

Markers currently registered:

| Marker        | Meaning                                                  |
|---------------|----------------------------------------------------------|
| `slow`        | > 1 s runtime                                            |
| `integration` | Cross-module integration tests                           |
| `pg`          | Requires a running Postgres (added by P4)                |
| `redis`       | Requires a running Redis (added by P5)                   |

## Branch protection (set manually in GitHub)

Required status checks once CI stabilises:

- `lint (ruff)`
- `typecheck (mypy)`
- `test (python 3.10)`
- `test (python 3.11)`

Plus:

- ≥ 1 review required.
- No force-push on `main`.

## Where to file what

- New proposals / designs → `openspec/changes/<kebab-name>/`
  (`proposal.md` + `design.md` + `tasks.md`).
- Completed changes → archive via `opsx/archive` (or the `openspec` CLI),
  landing under `openspec/changes/archive/YYYY-MM-DD-<name>/`.
- Capability specs (stable contracts) → `openspec/specs/<capability>/spec.md`.
- Project-wide rules → `AGENTS.md` (§19 holds the Change Log).

Happy shipping.
