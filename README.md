# rag-chat-cli

[![ci](https://github.com/juwenzhang/rag-chat-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/juwenzhang/rag-chat-cli/actions/workflows/ci.yml)

> 📖 **Language / 语言**：**English** · [简体中文](README.zh-CN.md)

A RAG-powered chat platform (CLI + Web) built on Ollama, Postgres + pgvector,
Redis and FastAPI. Architecture & roadmap lives in [AGENTS.md](AGENTS.md); the
concrete build plan lives in [openspec/changes/](openspec/changes/).

## Roadmap (top-level changes)

- **P0** `bootstrap-settings-and-env` ✓ archived — single config entry (`settings.py` + `.env`)
- **P1** `restructure-cli-ui-opencode-style` ✓ archived — minimal CLI skeleton (`ui/` + `app/`)
- **P2** `split-core-domain-layer` ✓ archived — `core/` domain package (Ollama + ChatService)
- **P3** `setup-quality-gates-ci-cd` ✓ archived — ruff / mypy / pytest-cov / pre-commit / GitHub Actions
- **P4** `setup-db-postgres-pgvector-alembic` ✓ archived — database schema + async SQLAlchemy + Alembic
- **P5** `add-redis-and-workers` — queue & background workers
- **P6** `add-fastapi-rest-api` + `add-jwt-auth` — HTTP surface
- **P6** `add-sse-and-websocket-streaming` — streaming responses
- **P7** `implement-rag-retrieval-pgvector` — retrieval pipeline
- **P8** `bootstrap-web-vite-react-ts` + `build-web-views-auth-chat-knowledge` — Web UI
- **P9** `add-observability-otel` + `setup-quality-gates-ci-cd` + `containerize-with-docker-compose`

See `openspec list` for live status.

## Requirements

- Python >= 3.10
- [uv](https://github.com/astral-sh/uv) for dependency management
- Ollama running locally (for dev)
- Postgres with pgvector and Redis (ships via `docker-compose.yml` once P3+P4 land)

## Installation

```bash
# Core runtime only
uv sync

# Core + dev tools (pytest, ruff, etc.) — recommended for contributors
uv sync --all-extras
```

## First Run

Copy the example environment file and edit as needed:

```bash
cp .env.example .env
```

All environment variables are declared in `settings.py` (pydantic-settings).
See `AGENTS.md` §7 for the full list.

## Configuration

All configuration goes through [settings.py](settings.py) (pydantic-settings)
with `.env` overrides. See [AGENTS.md](AGENTS.md) §7 for the full field list.

Environment variables are grouped by concern (app / auth / db / redis / ollama
/ retrieval / rate_limit) and support both flat names (`JWT_SECRET`) and
nested names (`AUTH__JWT_SECRET`).

## Database (Postgres + pgvector)

The DB layer is **optional** for running the CLI — the chat loop still works
with file-based memory when Postgres is unreachable. Bring up the database
when you want to exercise the full schema (P4+):

```bash
# 1. Start postgres (pgvector/pgvector:pg16) via docker compose
make db.up

# 2. Initialise: connect-probe + alembic upgrade head + assert pgvector installed
make db.init
# → [db-init] connectivity: OK
#   [db-init] migrations: at head
#   [db-init] pgvector: installed

# Optional: open a psql shell inside the container
make db.shell
```

Unit tests use SQLite in-memory by default (no docker required):
`make test`. The `pgvector`-specific integration tests are opt-in via
`pytest -m pg` once `make db.up` is running.

## Usage

The CLI entry is [main.py](main.py), a thin shim that delegates to [app/cli.py](app/cli.py).

```bash
# Show all subcommands
uv run python main.py --help

# Interactive chat (default subcommand)
uv run python main.py chat
uv run python main.py          # same thing

# Not-yet-implemented stubs (exit code 2)
uv run python main.py serve    # FastAPI server (lands in P5)
uv run python main.py train    # LoRA trainer
uv run python main.py ingest   # knowledge ingestion
```

### Chat keybindings (AGENTS.md §11)

| Key | Action |
|---|---|
| `Esc` + `Enter` | Send multi-line message |
| `F2` | Send (alternative) |
| `↑` / `↓` | History (persisted at `~/.config/rag-chat/history`) |
| `Ctrl-L` | Clear screen |
| `Ctrl-D` / `/quit` / `/exit` | Exit |
| `/help` | List all slash commands |
| `/clear` | Clear screen |
| `/new` | Start a fresh local session (clears in-memory history) |
| `/model` `/retrieve` `/login` `/logout` | Reserved (prints "not implemented yet") |

> The default reply provider in P1 is an in-process `EchoReplyProvider` — it
> echoes your input back as streaming tokens so the full render pipeline is
> verifiable without a running Ollama. Real LLM streaming is wired in by the
> next change, `split-core-domain-layer` (P2).

### Quality gates

```bash
uv run pytest -q
uv run ruff check ui/ app/ main.py
uv run --with mypy mypy ui/ app/
```

## Project Structure

```
├── AGENTS.md                # Architecture blueprint (source of truth)
├── settings.py              # Single config entry (pydantic-settings)
├── .env.example             # Environment variable template
├── main.py                  # CLI shim → app.cli.main
├── app/                     # Orchestration layer (the only layer that sees both ui/ and core/)
│   ├── cli.py               #   argparse entry (chat / serve / train / ingest)
│   └── chat_app.py          #   run_chat loop + ReplyProvider protocol
├── ui/                      # Presentation layer (rich + prompt_toolkit)
│   ├── theme.py             #   frozen color palette
│   ├── console.py           #   Console factory, banner, divider
│   ├── markdown.py          #   incremental Markdown rendering
│   ├── chat_view.py         #   Event TypedDict + ChatView
│   └── prompt.py            #   PromptSession + SlashDispatcher
├── tests/                   # pytest (unit + integration)
├── openspec/                # Specs & change proposals (施工图)
├── Makefile                 # Day-to-day commands
├── docker-compose.yml       # Service stack (postgres + redis + ollama + api)
├── pyproject.toml           # Python dependencies (uv-managed)
└── README.md                # This file
```

Layering rules live in AGENTS.md §3 / §3.1 — `ui/` never imports `core/` `db/` or `api/`.

## License

MIT
