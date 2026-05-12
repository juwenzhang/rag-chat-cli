# rag-chat-cli

[![ci](https://github.com/juwenzhang/rag-chat-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/juwenzhang/rag-chat-cli/actions/workflows/ci.yml)

> 📖 **Language / 语言**：**English** · [简体中文](README.zh-CN.md)

A ReAct agent for the terminal — runs locally against Ollama or any
OpenAI-compatible endpoint, with hybrid-retrieval RAG (Postgres +
pgvector), MCP tool integration, persistent per-user memory, and a
FastAPI surface that streams the same events over SSE / WebSocket to
any other UI you want to bolt on.

The architecture blueprint lives in [AGENTS.md](AGENTS.md). The streaming
event vocabulary is documented in [docs/STREAM_PROTOCOL.md](docs/STREAM_PROTOCOL.md).

## Highlights

- **ReAct loop** — multi-step tool calls with `thought` / `tool_call` /
  `tool_result` events, bounded by configurable `ResourceLimits`
  (`max_steps`, per-step tool cap, per-call timeout).
- **Two LLM backends, one protocol** — `OllamaClient` (local) and
  `OpenAIClient` (OpenAI / vLLM / Together / Groq / any compatible
  server) implement the same `LLMClient` protocol. Swap providers
  without touching the agent.
- **MCP integration** — stdio JSON-RPC client + `McpTool` adapter so
  any [Model Context Protocol](https://modelcontextprotocol.io) server
  shows up as a regular tool to the agent.
- **Hybrid retrieval RAG** — `PgvectorKnowledgeBase` combines vector
  search (pgvector) with `pg_trgm` lexical scoring via Reciprocal Rank
  Fusion, plus a pluggable `Reranker` hook. Citations are injected as
  `[N]` markers and surface back in the CLI / API.
- **Two-mode knowledge curation** — `/save` and `/reflect`
  (critic-gated auto-save) work against both the on-disk
  `FileKnowledgeBase` (logged-out, lives at `~/.config/rag-chat/kb/`)
  and Postgres `PgvectorKnowledgeBase` (logged-in). `/kb sync`
  migrates the local store into pgvector on first login.
- **Persistent memory** — per-session chat history (file or Postgres),
  per-user long-term memory with a `FactExtractor` hook,
  context-window-aware history summarization.
- **Streaming everywhere** — same `Event` type renders in the CLI,
  flows out of `POST /chat/stream` (SSE), and through `/ws/chat`
  (WebSocket with abort support).
- **Background workers** — Redis-backed FIFO queue + a `Worker` pump
  for off-loading expensive ingestion / re-index jobs out of the
  request path.
- **Observability shim** — optional OpenTelemetry tracer
  (no-op when OTel isn't installed) plus a `UsageAccumulator` that
  normalizes token / cost data across providers.

## Architecture

```
main.py
└─ app/cli.py            {chat, serve, ingest, worker, train}
   └─ app/chat_app.py    REPL + factory wiring
      └─ core/chat_service.py        ReAct loop (all the levers)
         ├─ core/llm/                {OllamaClient, OpenAIClient} : LLMClient
         ├─ core/tools/              ToolRegistry + FunctionTool + (MCP) McpTool
         ├─ core/knowledge/          PgvectorKnowledgeBase + Reranker + Ingestor
         ├─ core/memory/             {File,Db}ChatMemory + UserMemoryStore
         ├─ core/tokens.py           Tokenizer + TokenBudget
         ├─ core/history.py          HistorySummarizer
         ├─ core/prompts.py          PromptBuilder
         ├─ core/limits.py           ResourceLimits
         ├─ core/observability.py    Tracer + UsageAccumulator
         ├─ core/mcp/                stdio JSON-RPC client + adapter
         ├─ core/workers/            Redis queue + worker
         └─ core/streaming/          Event vocabulary + AbortContext

api/  → shares ChatService.generate() with the CLI; adds SSE / WS framing + auth deps
```

Every module is Protocol-backed. Adding (say) an Anthropic LLM client,
a Cohere reranker, a Postgres-backed queue or an HTTP MCP transport
is a single-file change that doesn't touch `ChatService`.

## Requirements

- Python ≥ 3.10
- [uv](https://github.com/astral-sh/uv) for dependency management
- A running Ollama (or an `OPENAI_API_KEY` for an OpenAI-compatible
  endpoint)
- Docker (for Postgres + pgvector + Redis via `docker-compose.yml`)

## Day 0 — clone to first reply

This is the canonical "I just cloned the repo, get me to a working
chat in five minutes" path. Every command is copy-paste ready.

```bash
# 1. Install Python deps
uv sync --all-extras

# 2. Make sure Ollama is running and pull the two models the CLI uses:
#    - the chat model (defaults to qwen2.5:1.5b — adjust as you wish)
#    - the embed model (required for /save, /reflect, /kb search, RAG)
ollama serve &                       # in a separate terminal if not already up
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text         # MUST pull this — /save will error 404 otherwise

# 3. Configure environment
cp .env.example .env
# Edit .env: change @postgres → @localhost for DATABASE_URL
#   DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5432/ragdb
# Generate a strong JWT secret (replaces the placeholder):
openssl rand -hex 32                 # paste into JWT_SECRET=... in .env

# 4. Bring up Postgres + apply migrations (idempotent)
make db.up                           # docker compose up postgres + pgvector
make db.init                         # connect probe + alembic upgrade head + pgvector check

# 5. Launch the REPL
make dev.cli                         # = uv run python -m main chat
```

You should see the model banner and a prompt. Type `/` to see the
slash-command autocomplete menu pop up, type a question to start
chatting.

> Skipped step 2 and `/save` fails with "model 'nomic-embed-text' not
> found"? Run `ollama pull nomic-embed-text` and retry — no restart
> needed.

> Skipped step 4 and want to use the local file KB only? You can — the
> CLI works against `~/.config/rag-chat/kb/` without a database. Just
> know that `/login` and the Postgres-backed RAG path won't work.

## Quickstart — CLI controls

Inside the REPL:

- Type `/` and the **autocomplete menu** pops up — arrow-keys or `Tab`
  to pick a command, each entry shows a one-line description.
- Type `/help` to render the full command panel (grouped, framed).
- `Enter` sends; `Ctrl+J` inserts a newline; `↑`/`↓` recalls history
  (persisted at `~/.config/rag-chat/history`); `Ctrl+L` clears.

### Slash commands

| Group | Command | What it does |
|---|---|---|
| **session** | `/sessions [id\|idx]` | List saved sessions (with arg, jumps like `/switch`) |
| | `/switch [id\|idx]` | Pick a session (no arg = list + prompt) |
| | `/new [title]` | Start a fresh conversation |
| | `/title <text>` | Rename the current conversation |
| | `/delete` | Delete the current conversation |
| **model** | `/model` | List pulled Ollama models |
| | `/model <name>` | Switch model at runtime (no restart) |
| | `/model pull <name>` | Download a model from the registry |
| **runtime** | `/rag [on\|off]` | Toggle retrieval-augmented context |
| | `/think [on\|off]` | Toggle deep-thinking hint (UI only) |
| **knowledge** | `/kb` | KB summary (count + recent docs + active backend) |
| | `/kb list` | List documents in the active KB |
| | `/kb show <idx\|id>` | Show one document's metadata + first chunks |
| | `/kb search <query>` | Preview retrieval (no LLM call — pure scoring) |
| | `/kb delete <idx\|id>` | Delete a document and its chunks (confirms) |
| | `/kb sync` | Push local KB → pgvector (logged-in only) |
| | `/save [title]` | Persist last Q+A turn into the active KB |
| | `/reflect [on\|off\|<0..1>]` | Auto-save high-quality turns (threshold-gated) |
| **auth** | `/register` | Create a new account |
| | `/login` | Log in (token persisted at `~/.config/rag-chat/token.json`, mode 0600) |
| | `/logout` | Revoke refresh token and clear local token |
| | `/whoami` | Print current user id |
| | `/ollama-auth [key\|clear\|show]` | Set/clear the Bearer key for hosted Ollama |
| **misc** | `/clear` | Clear the screen |
| | `/help` | Show the command panel |
| | `/quit` (`/exit`) | Exit the REPL |

### Knowledge curation

The knowledge commands work against the **active** KB, which is
selected by your auth state:

- **Logged out** → `FileKnowledgeBase` at `~/.config/rag-chat/kb/`
  (on-disk JSONL + stdlib-cosine search). Zero external dependencies
  beyond the embed model. `/kb` operations stay on your machine.
- **Logged in** (`/login`) → `PgvectorKnowledgeBase` against Postgres.
  Same admin API (`list`, `show`, `search`, `delete`, plus
  `add_document` via `/save`), backed by `vector(768)` columns and an
  ivfflat index. Documents are scoped to your `user_id`.

Typical curation flows:

```
# Manual save — explicit, single Q+A
> ask something useful
> /save
saved → local · 1a2b3c4d · ... · /kb show 1a2b3c4d

# Auto-save — critic LLM judges every turn, persists if confident
> /reflect on
> /reflect 0.7                # threshold (0-1); higher = stricter
> ask things — saves happen behind the scenes when warranted

# Migrate: local accumulation → pgvector after you log in
> /login
> /kb sync                    # re-embeds and copies local docs into PG
```

`/reflect` writes "fact cards" with the critic's distilled summary
alongside the original Q+A, tagged `auto-saved` so you can
`/kb list` and filter visually. Default off — turn it on explicitly.

## Quickstart — API

Assumes you've done [Day 0](#day-0--clone-to-first-reply) — Postgres
is up, migrations are at head, `.env` has a real `JWT_SECRET`. Then:

```bash
make dev.api              # = uvicorn api.app:create_app, reload mode
# or:
make dev.api PORT=8001    # if 8000 is taken
```

> SQLite (`DATABASE_URL=sqlite+aiosqlite:///./.dev.db`) is still
> wired for the test suite and zero-install route smoke-tests, but
> not recommended as a dev default: the Pgvector retriever uses
> `Vector` columns and `pg_trgm` operators that SQLite doesn't
> implement, so `/chat/stream` with RAG will error at query time.

Smoke:

```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"password1demo"}'
# 201 + {"id":"…","email":"me@example.com",…}
```

### REST / SSE / WebSocket reference

| Method | Path | Auth | Notes |
|---|---|---|---|
| `GET` | `/health` | public | liveness |
| `POST` | `/auth/register` | public | |
| `POST` | `/auth/login` | public | returns access + refresh |
| `POST` | `/auth/refresh` | refresh token | rotation enabled |
| `POST` | `/auth/logout` | refresh token | |
| `GET` `PATCH` | `/me` | bearer | |
| `POST` `GET` | `/chat/sessions` | bearer | |
| `GET` | `/chat/sessions/{id}/messages` | bearer | |
| `POST` | `/chat/messages` | bearer | non-streaming (aggregates SSE) |
| `POST` | `/chat/stream` | bearer | **SSE** — events: `retrieval` / `token` / `thought` / `tool_call` / `tool_result` / `done` / `error` |
| `WS` | `/ws/chat` | bearer (`bearer,<jwt>` subprotocol or `?token=<jwt>`) | supports `{"type":"abort"}` |
| `POST` `GET` | `/knowledge/documents` | bearer | |
| `POST` | `/knowledge/documents:reindex` | bearer | enqueues to the worker (202) |
| `GET` | `/knowledge/search` | bearer | |

Full event vocabulary + ordering rules: [docs/STREAM_PROTOCOL.md](docs/STREAM_PROTOCOL.md).

`make openapi` regenerates [docs/openapi.json](docs/openapi.json);
`make test.api` runs the route suite against an in-memory SQLite via
`httpx.ASGITransport`.

## Ingestion + background workers

```bash
# Inline ingestion (CLI blocks until done)
uv run python -m main ingest path/to/dir --recursive --title "My docs"

# Enqueue to the worker queue and return immediately
uv run python -m main ingest path/to/dir --recursive --async

# Run the worker (terminal B)
uv run python -m main worker
# → [worker] ingested /x/a.md → doc=… chunks=12
```

Job spec, queue protocol and retry expectations live in
[`core/workers/queue.py`](core/workers/queue.py).

## Configuration

All knobs are declared in [settings.py](settings.py) (pydantic-settings)
and overridable via `.env`. Variables are grouped by concern and accept
both flat names (`JWT_SECRET`) and nested names
(`AUTH__JWT_SECRET`) — nested wins on conflict.

| Group | Flat env keys | What it controls |
|---|---|---|
| `app` | `APP_ENV`, `APP_HOST`, `APP_PORT`, `LOG_LEVEL` | runtime |
| `auth` | `JWT_SECRET`, `JWT_ALG`, `ACCESS_TTL_MIN`, `REFRESH_TTL_DAYS` | auth |
| `db` | `DATABASE_URL`, `DB_POOL_SIZE`, `ECHO_SQL` | persistence |
| `redis` | `REDIS_URL` | worker queue + caching |
| `ollama` | `OLLAMA_BASE_URL`, `OLLAMA_CHAT_MODEL`, `OLLAMA_EMBED_MODEL`, `OLLAMA_API_KEY` | local / hosted Ollama |
| `openai` | `OPENAI_BASE_URL`, `OPENAI_CHAT_MODEL`, `OPENAI_EMBED_MODEL`, `OPENAI_API_KEY`, `OPENAI_ORGANIZATION` | OpenAI-compatible endpoints |
| `retrieval` | `RETRIEVAL_ENABLED`, `RETRIEVAL_TOP_K`, `RETRIEVAL_MIN_SCORE`, `RETRIEVAL_EMBED_DIM` | RAG defaults |
| `rate_limit` | `RATE_LIMIT_PER_MIN` | API throttle |

`APP_ENV=prod` refuses to boot unless `JWT_SECRET` is a non-placeholder
value. Generate one with `openssl rand -hex 32`.

## Database & migrations

The DB is **optional** for the CLI — chat works with file memory when
Postgres is unreachable. Bring it up when you want the full schema:

```bash
make db.up          # postgres + pgvector via docker compose
make db.init        # connect-probe + alembic upgrade head + pgvector check
make db.shell       # interactive psql
```

Migration history:

- `0001_init` — users, chat sessions, messages, documents, chunks, refresh tokens
- `0002_add_tool_message_fields` — `messages.tool_call_id` + `messages.tool_calls` (JSONB on Postgres) for tool-role turns
- `0003_add_user_memories` — `user_memories` table for long-term per-user facts

Unit tests use SQLite in-memory by default (no docker). pgvector-specific
integration tests are opt-in via `pytest -m pg`.

## Development

```bash
make ci             # ruff check + format check + mypy strict + pytest
make lint           # ruff check
make fmt            # ruff format (write)
make typecheck      # mypy --strict on app/ core/ ui/ api/ db/
make test           # all tests
make test-fast      # skip slow / pg / redis / integration markers
make test-cov       # pytest-cov (soft gate)
make test-cov-strict   # enforce AGENTS.md §12 thresholds
make openapi        # regenerate docs/openapi.json
make openapi.check  # diff schema against docs/openapi.json (CI)
```

Pre-commit hooks: `pre-commit install` once, then ruff + format run on
every commit.

## Project structure

```
├── AGENTS.md                  # architecture blueprint (single source of truth)
├── docs/
│   ├── STREAM_PROTOCOL.md     # streaming event vocabulary
│   └── openapi.json           # generated; CI checks for drift
├── settings.py                # pydantic-settings entry
├── .env.example               # env template
├── main.py                    # CLI shim → app.cli.main
├── app/                       # orchestration (only layer that touches both ui/ and core/)
│   ├── cli.py                 #   argparse: chat / serve / ingest / worker / train
│   ├── chat_app.py            #   REPL + ChatService factory
│   └── auth_local.py          #   ~/.config/rag-chat/token.json
├── ui/                        # presentation (rich + prompt_toolkit)
│   ├── theme.py · console.py · markdown.py
│   ├── chat_view.py           #   stream renderer + help panel
│   └── prompt.py              #   PromptSession + SlashCompleter + Dispatcher
├── core/                      # domain layer (provider-agnostic, no I/O imports)
│   ├── chat_service.py        #   ReAct loop — single integration point
│   ├── llm/                   #   LLMClient protocol + Ollama + OpenAI impls
│   ├── tools/                 #   Tool protocol + ToolRegistry + FunctionTool
│   ├── knowledge/             #   PgvectorKnowledgeBase + Ingestor + Reranker hook
│   ├── memory/                #   ChatMemory (File/DB) + UserMemoryStore + FactExtractor
│   ├── mcp/                   #   MCP stdio client + Tool adapter
│   ├── workers/               #   RedisJobQueue + Worker pump
│   ├── streaming/             #   Event TypedDict + AbortContext
│   ├── tokens.py · history.py · prompts.py · limits.py · observability.py
│   └── auth/                  #   bcrypt + JWT + refresh rotation
├── db/                        # SQLAlchemy 2.x async + models
├── alembic/versions/          # 0001 / 0002 / 0003
├── api/                       # FastAPI app (routers / deps / middleware)
├── scripts/                   # one-shot ops (db_init, check_coverage, …)
├── tests/                     # pytest (unit + integration + api)
├── openspec/                  # spec proposals + archives
├── Makefile · docker-compose.yml · pyproject.toml
└── README.md / README.zh-CN.md
```

Layering rules (AGENTS.md §3): `ui/` never imports `core/` / `db/` / `api/`;
`core/` never imports `db/` / `api/` / `ui/`; `app/` is the only layer
allowed to wire everything together.

## Contributing

- New proposals → `openspec/changes/<kebab-name>/` (`proposal.md` +
  `design.md` + `tasks.md`).
- Finished changes → archived under
  `openspec/changes/archive/YYYY-MM-DD-<name>/`.
- Stable capability specs → `openspec/specs/<capability>/spec.md`.

Run `make ci` before opening a PR — the four quality gates (ruff +
format + mypy + pytest) must be green.

## License

MIT
