---
title: Rag Chat Backend
emoji: 🤖
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# rag-chat-cli

[![ci](https://github.com/juwenzhang/rag-chat-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/juwenzhang/rag-chat-cli/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)
[![Node](https://img.shields.io/badge/node-20+-green.svg)](clients/tui/package.json)

> 📖 **Language / 语言**：**English** · [简体中文](README.zh-CN.md)

A self-hostable, end-to-end stack for chatting with your **own**
LLMs — local-first via Ollama, cloud-friendly via OpenAI-compatible
endpoints — with retrieval-augmented memory, agentic tool calls, and
two first-class clients (a polished web app and an Ink terminal).

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   Next.js Web  ──┐                            ┌─►  Ollama        │
│                  │                            │                  │
│   Ink TUI    ────┼──►  FastAPI  ──►  Service ─┤                  │
│                  │  (REST + SSE)              │    pgvector RAG  │
│   Your client ───┘                            └─►  MCP tools     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Table of contents

- [Why this exists](#why-this-exists)
- [Screenshots](#screenshots)
- [Highlights](#highlights)
- [Architecture](#architecture)
- [Quickstart — local stack](#quickstart--local-stack)
- [The Ink TUI (`lhx-rag`)](#the-ink-tui-lhx-rag)
- [The Web client](#the-web-client)
- [REST / SSE reference](#rest--sse-reference)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Documentation index](#documentation-index)
- [License](#license)

---

## Why this exists

Most "chat with your data" demos ship as a notebook or a hosted
SaaS — neither survives contact with a real workflow. **rag-chat-cli**
treats the chat layer as production software:

| Concern | What we do |
| --- | --- |
| **Local first** | Ollama is the reference backend. OpenAI-compatible providers (vLLM, Groq, OpenRouter, …) are second-class only because they ship later in the boot sequence. |
| **Real persistence** | Postgres for sessions, messages, memory, knowledge; pgvector for embeddings; Redis for the worker queue. No "in-memory store" tricks. |
| **Two real UIs** | A Next.js web app (RSC + streaming) and an Ink terminal client share one OpenAPI surface. Anything one can do, the other can do. |
| **Multi-client auth** | A dedicated `/v1/*` sub-app with per-client allowlists isolates non-browser traffic from the website's CORS policy, so reverse proxies (HF Spaces, CDNs) can't break the CLI. See [docs/backend/MULTI_CLIENT_AUTH_DESIGN.md](docs/backend/MULTI_CLIENT_AUTH_DESIGN.md). |
| **Stable streaming protocol** | One `Event` vocabulary (`token`, `thought`, `tool_call`, `tool_result`, `retrieval`, `done`, `error`) flows over SSE — clients render it the same way. See [docs/backend/STREAM_PROTOCOL.md](docs/backend/STREAM_PROTOCOL.md). |

---

## Screenshots

### Web — landing (signed-in, Chinese UI)

![Web home — Chinese](https://github.com/juwenzhang/rag-chat-cli/raw/master/docs/images/web-home-zh.png)

### Web — sign-in card

![Web login — Chinese](https://github.com/juwenzhang/rag-chat-cli/raw/master/docs/images/web-login-zh.png)

### Web — landing (English UI)

![Web home — English](https://github.com/juwenzhang/rag-chat-cli/raw/master/docs/images/web-home-en.png)

### Web — sign-in (English UI)

![Web login — English](https://github.com/juwenzhang/rag-chat-cli/raw/master/docs/images/web-login-en.png)

### Terminal — sign-in

![TUI login](https://github.com/juwenzhang/rag-chat-cli/raw/master/docs/images/tui-login.png)

### Terminal — three-pane chat

![TUI shell](https://github.com/juwenzhang/rag-chat-cli/raw/master/docs/images/tui-shell.png)

> The terminal client (`lhx-rag`) is a fullscreen Ink app: sessions on
> the left, transcript in the middle, composer at the bottom, and a
> live model / provider footer pinned to the sidebar.

---

## Highlights

- **ReAct agent loop** — multi-step tool calls emitted as
  `thought` / `tool_call` / `tool_result` events, bounded by
  configurable `ResourceLimits` (`max_steps`, per-step tool cap,
  per-call timeout).
- **Two LLM backends, one protocol** — `OllamaClient` (local) and
  `OpenAIClient` (OpenAI / vLLM / Together / Groq / any compatible
  endpoint) implement the same `LLMClient`. Swap providers without
  touching `ChatService`.
- **First-class provider management** — `Provider` rows store the
  per-user routing (base URL, encrypted API key, "is default"
  flag). Both clients can list / add / test / pull / delete via the
  same REST surface.
- **Hybrid-retrieval RAG** — `PgvectorKnowledgeBase` combines vector
  search (pgvector) with `pg_trgm` lexical scoring via Reciprocal
  Rank Fusion, plus a pluggable `Reranker` hook. Citations are
  injected as `[N]` markers and surface back in the CLI / web UI.
- **MCP integration** — stdio JSON-RPC client + `McpTool` adapter so
  any [Model Context Protocol](https://modelcontextprotocol.io)
  server appears as a regular tool to the agent.
- **Persistent memory** — per-session chat history, per-user
  long-term memory with a `FactExtractor` hook, context-window-aware
  history summarisation.
- **Streaming everywhere** — same `Event` shape over `POST /chat/stream`
  (SSE) for both clients. WebSocket variant with abort support.
- **Background workers** — Redis-backed FIFO queue + a `Worker` pump
  for off-loading expensive ingestion / re-index jobs out of the
  request path.
- **Multi-client auth split** — root path stays strict (browser-only
  CORS allowlist); a dedicated `/v1/*` sub-app gates traffic by an
  `X-Client-Id` allowlist instead. CLI, MCP servers and other
  non-browser callers don't ride on the website's policy any more.
- **Observability shim** — optional OpenTelemetry tracer (no-op when
  OTel isn't installed) plus a `UsageAccumulator` that normalises
  token / cost data across providers.

---

## Architecture

```
api/                            FastAPI app
   ├─ app.py                    root + /v1 sub-app, middleware ordering
   ├─ middleware/               ClientId allowlist, path-filtered CORS
   └─ routers/                  REST endpoints (auth, chat, knowledge,
                                providers, sessions, shares, …)

clients/
   └─ tui/                      Ink (React for the terminal) — `lhx-rag`

websites/                       Next.js 15 (RSC) + Tailwind + Server Actions

service/                        backend domain layer
   ├─ chat/                  ChatService + prompts / titles / history /
   │                         tokens / limits
   ├─ llm/                   {Ollama,OpenAI}Client : LLMClient
   ├─ providers/             provider registry + runtime resolution
   ├─ knowledge/             PgvectorKnowledgeBase + Reranker + Ingestor
   ├─ memory/                {File,Db}ChatMemory + UserMemoryStore
   ├─ db/                    SQLAlchemy async models / session factory
   ├─ tools/                 ToolRegistry + FunctionTool + McpTool
   ├─ mcp/                   stdio JSON-RPC client + adapter
   ├─ workers/               Redis queue + worker
   ├─ streaming/             Event vocabulary + AbortContext
   └─ common/                shared infrastructure
```

Every module is Protocol-backed. Adding (say) an Anthropic LLM client,
a Cohere reranker, a Postgres-backed queue or an HTTP MCP transport
is a single-file change that doesn't reach into `ChatService`.

---

## Quickstart — local stack

> Requirements: **Python ≥ 3.10**, [uv](https://github.com/astral-sh/uv),
> Docker (for Postgres + pgvector + Redis), and a running Ollama
> *or* an `OPENAI_API_KEY`. Optional: **Node ≥ 20** for the web /
> Ink clients.

```bash
# 1. Clone and install backend deps
git clone https://github.com/juwenzhang/rag-chat-cli
cd rag-chat-cli
uv sync

# 2. Pull the chat + embed + vision models you want to use
ollama pull qwen3-coder-next:cloud   # chat default; pick anything you like
ollama pull nomic-embed-text         # required for /save, /reflect, RAG
ollama pull qwen3-vl:235b-cloud      # required for image captions

# 3. Configure the environment
cp .env.example .env
# Edit .env:
#   - DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5432/ragdb
#   - JWT_SECRET=<openssl rand -hex 32>
#   - OLLAMA_BASE_URL=http://localhost:11434
#   - APP_ALLOWED_CLIENT_IDS=lhx-rag-cli  (already set, see Configuration)

# 4. Bring up Postgres + Redis and apply migrations (idempotent)
make db.up
make db.migrate

# 5. Run the FastAPI server (auto-reload)
make dev.api
# → http://localhost:8000  (root strict CORS for the website,
#                          /v1/* permissive for X-Client-Id callers)
```

Two clients to choose from:

```bash
# Ink terminal client — fullscreen, three panes
make dev.cli            # or: cd clients/tui && pnpm dev

# Next.js website
make dev.web            # or: cd websites && pnpm dev

# Or start all three at once (needs tmux)
make dev.all
```

---

## The Ink TUI (`lhx-rag`)

A fullscreen Ink app that talks **only** to the FastAPI `/v1` surface.
Built with `ink` + `zustand` + `marked` (for terminal markdown).

### What you get

- **Three focusable panes** — sessions, transcript, composer; cycle with
  `Tab` / `Shift+Tab`.
- **Slash commands** with fuzzy completion + scrolling palette
  (`/help` lists everything).
- **Sidebar footer** that pins identity, API endpoint, current model,
  current provider, and the `rag` / `think` flags — so your shell prompt
  never lies about which model just answered.
- **Alt-screen buffer** — restores your previous shell scrollback on
  exit (set `LHX_RAG_NO_FULLSCREEN=1` to disable).
- **Per-account state isolation** — `/logout` clears the screen and the
  provider cache before re-rendering the login card.

### Slash commands (excerpt)

| Command | What it does |
| --- | --- |
| `/help` | Open the categorised command panel. |
| `/new [title]`, `/sessions`, `/switch <id\|index>`, `/title <text>` | Session management. |
| `/rag on\|off`, `/think on\|off\|low\|medium\|high` | Per-turn flags. |
| `/regenerate` (`/r`), `/stop`, `/edit <text>`, `/rmsg`, `/eval` | Chat actions. |
| `/model [<tag>\|set <provider> <tag>\|clear\|show]` | Inspect / switch the active session's model. Bare `/model` shows the current pin **plus** five available tags on the resolved provider. |
| `/pref [show\|set <key> <val>\|clear <key>]` | Per-user defaults: provider, model, embed, rag. |
| `/kb [list\|add\|rm\|reindex\|search <q>]` | Knowledge base management. |
| `/providers [list\|add\|rm\|default\|test]` | LLM provider routing. |
| `/models [list\|pull\|rm]` | Pull / delete models on a provider. |
| `/register <email> <password> [name]`, `/whoami`, `/logout` | Account flow. |
| `/quit` (`/q`) | Exit. |

The full design lives in
[clients/tui/README.md](clients/tui/README.md) (run `pnpm dev`
inside that directory to iterate).

---

## The Web client

`websites/` hosts a Next.js 15 (App Router + RSC) workspace with three
projects:

```
websites/
   ├─ apps/web/                 the user-facing chat app
   ├─ apps/admin/               admin tooling
   └─ packages/                 shared UI / utilities / locales
```

Highlights:

- **i18n** — Chinese and English share the same schema; the web home
  switches via the language toggle in the header.
- **Streaming** via Server Actions over SSE; the same `Event` shapes
  the TUI consumes.
- **Knowledge / provider / model management** — full UI for the same
  REST surface the CLI drives.
- **Org / wiki workspaces** — share knowledge across teams; not yet
  reflected in the TUI.

Deploy guides:
[docs/fe/DEPLOY_WEBSITES.md](docs/fe/DEPLOY_WEBSITES.md),
[docs/ops/DEPLOY_BACKEND_DOCKER.md](docs/ops/DEPLOY_BACKEND_DOCKER.md),
[docs/ops/DEPLOY_FREE_STACK.md](docs/ops/DEPLOY_FREE_STACK.md).

---

## REST / SSE reference

OpenAPI is auto-published at `GET /openapi.json` and the Swagger UI at
`GET /docs`. Highlights:

| Group | Endpoints |
| --- | --- |
| `auth` | `POST /v1/auth/{register,login,logout,refresh}` |
| `me` | `GET /v1/me`, `PATCH /v1/me`, `GET\|PUT /v1/me/preferences` |
| `chat` | `POST /v1/chat/sessions`, `GET /v1/chat/sessions`, `PATCH\|DELETE /v1/chat/sessions/{id}`, `GET /v1/chat/sessions/{id}/messages`, `POST /v1/chat/messages`, **`POST /v1/chat/stream`**, `POST /v1/chat/stream/regenerate`, `PATCH\|DELETE /v1/chat/messages/{id}`, `GET\|POST /v1/chat/messages/{id}/evaluation` |
| `knowledge` | `POST /v1/knowledge/documents`, `GET /v1/knowledge/documents`, `GET\|PATCH\|DELETE /v1/knowledge/documents/{id}`, `POST /v1/knowledge/documents:reindex`, `GET /v1/knowledge/search` |
| `providers` | `GET\|POST /v1/providers`, `PATCH\|DELETE /v1/providers/{id}`, `GET /v1/providers/{id}/models`, `POST /v1/providers/{id}/models/{meta,pull,delete,show}`, `POST /v1/providers/test` |
| `assets` | `POST /v1/assets/images`, `GET /v1/assets/{id}` |
| `shares / bookmarks / orgs / wikis` | full CRUD — see OpenAPI |

> **Browser callers** drop the `/v1` prefix and ride the root CORS
> allowlist; **non-browser callers** (the Ink TUI, MCP servers, your
> own scripts) hit `/v1/*` with `X-Client-Id: <allowlisted>`. Both
> share the same handlers — this is purely a middleware split.

The streaming event vocabulary (`token`, `thought`, `tool_call`,
`tool_result`, `retrieval`, `done`, `error`) is documented in
[docs/backend/STREAM_PROTOCOL.md](docs/backend/STREAM_PROTOCOL.md).

---

## Configuration

`.env.example` is the source of truth — copy it to `.env` and tweak.
Most settings have sensible defaults:

| Group | Vars | Notes |
| --- | --- | --- |
| `app` | `APP_ALLOWED_CLIENT_IDS` | Comma-separated allowlist for `/v1/*` traffic. Defaults to `lhx-rag-cli`. |
| `auth` | `JWT_SECRET`, `JWT_*_EXPIRES_MIN` | HS256 access + refresh tokens. |
| `db` | `DATABASE_URL`, `DB_POOL_SIZE`, `ECHO_SQL` | Async asyncpg URL. |
| `redis` | `REDIS_URL` | Worker queue + caching. |
| `ollama` | `OLLAMA_BASE_URL`, `OLLAMA_CHAT_MODEL`, `OLLAMA_EMBED_MODEL`, `OLLAMA_API_KEY`, `OLLAMA_THINK` | Local / hosted Ollama. |
| `openai` | `OPENAI_BASE_URL`, `OPENAI_CHAT_MODEL`, `OPENAI_EMBED_MODEL`, `OPENAI_API_KEY`, `OPENAI_ORGANIZATION` | OpenAI-compatible endpoints. |
| `retrieval` | `RAG_ENABLED`, `RAG_TOP_K`, `RAG_MIN_SCORE`, `RAG_EMBED_DIM`, `RAG_IMAGE_CAPTION_MODEL` | RAG defaults. |
| `evaluation` | `EVAL_ENABLED`, `EVAL_MODEL` | Resident judge for `/eval`. |
| `rate_limit` | `RATE_LIMIT_PER_MIN` | Per-IP global cap. |

### TUI-specific

`clients/tui/.env` is bundled at build time and re-read at dev time.
Recognised keys:

| Var | Default | Effect |
| --- | --- | --- |
| `DEFAULT_BASE_URL` | `http://127.0.0.1:8000` | Base URL baked into the published binary. |
| `RAG_API_BASE_URL` | _(unset)_ | Per-invocation override. Wins over `DEFAULT_BASE_URL`. |
| `LHX_RAG_NO_FULLSCREEN` | _(unset)_ | Set to `1` to skip the alt-screen buffer (handy for piped output / CI). |

Resolution order: `options.baseUrl` → `RAG_API_BASE_URL` →
`DEFAULT_BASE_URL` → loopback fallback.

---

## Project structure

```
.
├── alembic/                 DB migrations
├── api/                     FastAPI HTTP / SSE entrypoints
├── clients/tui/             Ink terminal client (`lhx-rag`)
├── deploy/                  Render + HF Space recipes
├── docs/                    architecture / deploy / design docs
│   └── images/              README screenshots
├── openspec/                living spec + change proposals
├── service/                 backend domain layer
├── websites/                Next.js workspace (web + admin)
├── settings.py              pydantic-settings + flat → nested mapping
├── pyproject.toml
├── docker-compose.yml
├── Dockerfile               backend image (also used by HF Space)
├── README.md                ← you are here
└── README.zh-CN.md          中文版 README
```

---

## Documentation index

- [docs/backend/MULTI_CLIENT_AUTH_DESIGN.md](docs/backend/MULTI_CLIENT_AUTH_DESIGN.md) — why `/v1` exists, device-flow roadmap.
- [docs/backend/STREAM_PROTOCOL.md](docs/backend/STREAM_PROTOCOL.md) — wire format for SSE events.
- [docs/backend/AUTH_DESIGN.md](docs/backend/AUTH_DESIGN.md) — JWT access / refresh, password policy.
- [docs/ai/CHAT_OBSERVABILITY_EVALUATION_VISION.md](docs/ai/CHAT_OBSERVABILITY_EVALUATION_VISION.md) — eval / vision pipeline.
- [docs/ollama/OLLAMA_CAPABILITIES_ADAPTATION.md](docs/ollama/OLLAMA_CAPABILITIES_ADAPTATION.md) — capability detection & fallbacks.
- [docs/ai/WEB_SEARCH_CONTEXT_OPTIMIZATION.md](docs/ai/WEB_SEARCH_CONTEXT_OPTIMIZATION.md) — tool result trimming.
- [docs/fe/FRONTEND_NEXT_OPTIMIZATION.md](docs/fe/FRONTEND_NEXT_OPTIMIZATION.md) — RSC / streaming notes.
- [docs/fe/FRONTEND_SSR_MVC.md](docs/fe/FRONTEND_SSR_MVC.md) — server-action layout for the web app.
- [docs/ops/DEPLOY_BACKEND_DOCKER.md](docs/ops/DEPLOY_BACKEND_DOCKER.md), [DEPLOY_WEBSITES.md](docs/fe/DEPLOY_WEBSITES.md), [DEPLOY_FREE_STACK.md](docs/ops/DEPLOY_FREE_STACK.md) — operator guides.
- [docs/backend/DEVELOPMENT.md](docs/backend/DEVELOPMENT.md) — local toolchain (uv, alembic, pre-commit).
- [openspec/](openspec/) — living spec; current `refactor/tui-refactor`
  branch hosts the TUI rewrite + multi-client auth phase 1.

---

## License

Released under the **MIT License**. You're free to use, modify and
redistribute as long as the copyright + permission notice stays.
