# Development Guide

> Companion to `AGENTS.md` — `AGENTS.md` states the **rules**,
> this doc states the **workflows**.

## Prerequisites

- **Python**: 3.10 is the current pinned version (`.python-version`).
  CI runs backend static checks on the pinned toolchain.
- **uv**: [`astral-sh/uv`](https://github.com/astral-sh/uv) 0.5+ —
  the only Python package/runtime manager this repo uses.
- **Docker** (optional, future): used once P4+ changes land the
  Postgres / Redis service containers.

## First-time setup

```bash
# 1. Clone & enter repo
git clone git@github.com:juwenzhang/rag-chat-cli.git
cd rag-chat-cli

# 2. Install the dev toolchain (ruff + mypy + pre-commit)
uv sync --extra dev

# 3. Create .env (safe defaults, dev-only placeholder secret)
make env

# 4. Install git hooks
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push
```

`make env` copies `.env.example` → `.env` unless one already exists.

## Frontend SSR/MVC workflow

The Next.js frontend under `websites/` follows an SSR-specific MVC discipline. Before changing frontend architecture or moving feature code, read:

- `docs/FRONTEND_SSR_MVC.md`
- `docs/FRONTEND_NEXT_OPTIMIZATION.md`
- `websites/src/features/README.md`
- `websites/AGENTS.md`

Short version:

- `app/**` is Server Controller.
- `features/*/hooks` is Client Controller.
- `features/*/services` and `features/*/stores` are Model.
- `features/*/components` is View.
- View code should not import browser API clients, imperative router APIs, or toast.
- Keep `lib/api/browser`, `lib/api/server`, and `lib/api/shared` boundaries intact.

## Daily workflow

| Task                      | Command              | Notes                                         |
|---------------------------|----------------------|-----------------------------------------------|
| Run interactive CLI       | `make dev.cli`       | Boots `python main.py chat`                   |
| Lint                      | `make lint`          | Ruff, read-only                               |
| Auto-fix lint             | `make lint-fix`      | Ruff + auto-fix                               |
| Format (write)            | `make fmt`           | Ruff format                                   |
| Format check              | `make fmt-check`     | Used by CI                                    |
| Type-check                | `make typecheck`     | Mypy over `api service tui main.py settings.py scripts` |
| Compile check             | `make compile`       | `compileall` syntax/import-path smoke check   |
| **Full CI simulation**    | `make ci`            | `lint + fmt-check + typecheck + compile`      |

`make help` prints all targets.

## Pre-commit

Commit hooks run Ruff, ESLint, Prettier, basic hygiene, and Angular-style commit message validation. Push hooks run the heavier backend/frontend checks (`mypy`, `compileall`, ESLint, Prettier check, and TypeScript).

```bash
# Run commit-stage hooks against the whole repo once:
uv run pre-commit run --all-files

# Run push-stage hooks manually:
uv run pre-commit run --hook-stage pre-push --all-files
```

## Branch protection (set manually in GitHub)

Required status checks once CI stabilises:

- `quality`

Plus:

- ≥ 1 review required.
- No force-push on `main`.

## Where to file what

- New proposals / designs → `openspec/changes/<kebab-name>/`
  (`proposal.md` + `design.md` + `tasks.md`).
- Completed changes → archive via `opsx/archive` (or the `openspec` CLI),
  landing under `openspec/changes/archive/YYYY-MM-DD-<name>/`.
- Capability specs (stable contracts) → `openspec/specs/<capability>/spec.md`.
- Project-wide rul
