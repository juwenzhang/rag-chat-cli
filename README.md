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
- **P5** `add-jwt-auth` ✓ archived — auth domain (bcrypt + JWT + refresh rotation) + CLI token store
- **P6** `add-fastapi-rest-api` ✓ archived — FastAPI app + routers + middleware + OpenAPI dump
- **P7** `add-sse-and-websocket-streaming` ✓ archived — `POST /chat/stream` (SSE) + `/ws/chat` (WebSocket) + abort + log sanitization
- **P8** `add-redis-and-workers` — queue & background workers
- **P9** `implement-rag-retrieval-pgvector` — retrieval pipeline
- **P10** `bootstrap-web-vite-react-ts` + `build-web-views-auth-chat-knowledge` — Web UI
- **P11** `add-observability-otel` + `containerize-with-docker-compose`

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

### Generating `JWT_SECRET`

`dev` falls back to an insecure placeholder with a warning. For anything
beyond a throwaway shell, generate a strong secret and put it in `.env`:

```bash
openssl rand -hex 32
```

`APP_ENV=prod` refuses to boot unless `JWT_SECRET` is a non-placeholder value.

### Quickstart: run the API on your laptop

The Docker-compose defaults in `.env.example` use service-network hostnames
(`postgres`, `redis`, `ollama`) that **do not resolve on your host machine**.
For running the API directly against Python:

```bash
# 1. Create .env from the template
cp .env.example .env

# 2. Pick one of these DATABASE_URLs — edit .env accordingly:
#    (a) zero-install, validates API + auth, no real RAG search:
#        DATABASE_URL=sqlite+aiosqlite:///./.dev.db
#    (b) real Postgres (recommended once you want RAG working):
#        make db.up     # starts pgvector/pgvector:pg16 on localhost:5432
#        DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5432/ragdb

# 3. Generate a strong JWT secret so you don't see the "insecure dev secret" warning
openssl rand -hex 32          # copy output into JWT_SECRET=... in .env

# 4. Initialise the schema (idempotent — safe to re-run)
make db.init

# 5. Start the API (auto-reload). PORT=xxx if 8000 is taken:
make dev.api                   # or: make dev.api PORT=8001
# Prefer one-shot: `make dev` = db.init + dev.api in sequence.

# Port stuck? `make dev.kill` frees PORT=$PORT (default 8000).
```

Smoke:

```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"password1demo"}'
# 201 + {"id":"…","email":"me@example.com",…}
```

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

# Run the FastAPI server (P6 onwards)
uv run python main.py serve --host 127.0.0.1 --port 8000
# → /docs UI, /openapi.json, /health, /auth/*, /me, /chat/*, /knowledge/*

# Not-yet-implemented stubs (exit code 2)
uv run python main.py train    # LoRA trainer
uv run python main.py ingest   # knowledge ingestion
```

### REST API quick reference (P6)

| Method | Path | Auth |
|---|---|---|
| `GET` | `/health` | public |
| `POST` | `/auth/register` | public |
| `POST` | `/auth/login` | public |
| `POST` | `/auth/refresh` | public (refresh token) |
| `POST` | `/auth/logout` | public (refresh token) |
| `GET` `PATCH` | `/me` | bearer |
| `POST` `GET` | `/chat/sessions` | bearer |
| `GET` | `/chat/sessions/{id}/messages` | bearer |
| `POST` | `/chat/messages` | bearer (non-streaming, aggregates SSE) |
| `POST` | `/chat/stream` | bearer — SSE, events: `retrieval / token / done / error` |
| `WS` | `/ws/chat` | bearer (subprotocol `bearer,<jwt>` or `?token=<jwt>`); supports `{"type":"abort"}` |
| `POST` `GET` | `/knowledge/documents` | bearer |
| `POST` | `/knowledge/documents:reindex` | bearer (202 stub until P8) |
| `GET` | `/knowledge/search` | bearer (empty until P9) |

`make openapi` regenerates [docs/openapi.json](docs/openapi.json); `make test.api`
runs the route tests against an in-memory SQLite via `httpx.ASGITransport`.

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
| `/login` | Interactive email + password → stores JWT at `~/.config/rag-chat/token.json` (0600) |
| `/logout` | Revoke the current refresh token and clear the local token file |
| `/whoami` | Print the user id decoded from the stored access token |
| `/model` `/retrieve` | Reserved (prints "not implemented yet") |

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
