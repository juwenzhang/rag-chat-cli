# lhx-rag Web (websites/)

Next.js 16 frontend for the [rag-chat-cli](../) FastAPI backend.

## Architecture

This app implements the **BFF (Backend for Frontend) pattern**:

```
Browser  ─HTTP─►  Next.js (this app)  ─HTTP+Bearer─►  FastAPI (../api/)
         cookies          server-side                   port 8000
         only
```

- The browser **only** talks to Next.js (same origin → cookies trivially work).
- Next.js holds the session in an **HttpOnly cookie** and forwards requests
  to FastAPI with a `Authorization: Bearer` header server-side.
- FastAPI is never directly exposed to the browser, so token theft via XSS
  is structurally prevented.

See [`../docs/ROADMAP.md`](../docs/ROADMAP.md) and
[`../docs/backend/AUTH_DESIGN.md`](../docs/backend/AUTH_DESIGN.md) for the full design.

## Quick start

```bash
# 1. Start FastAPI in another terminal
cd .. && make dev.api

# 2. Configure
cp .env.example .env.local
# edit RAG_API_URL if your backend isn't on localhost:8000

# 3. Install + run
pnpm install
pnpm dev
# → http://localhost:3000
```

First visit redirects to `/login`. Register once with a valid email +
8-char password to enter `/chat`.

## Scripts

| Command             | What it does                         |
| ------------------- | ------------------------------------ |
| `pnpm dev`          | Dev server with Turbopack            |
| `pnpm build`        | Production build                     |
| `pnpm start`        | Run production build                 |
| `pnpm lint`         | ESLint check                         |
| `pnpm lint:fix`     | ESLint auto-fix                      |
| `pnpm format`       | Prettier write                       |
| `pnpm format:check` | Prettier check                       |
| `pnpm typecheck`    | TypeScript `tsc --noEmit`            |
| `pnpm verify`       | ESLint + Prettier check + TypeScript |

## Layout

```
src/
├── app/
│   ├── (auth)/            # /login, /register — public
│   │   ├── login/
│   │   └── register/
│   ├── (app)/             # protected — sidebar shell
│   │   └── chat/[sessionId]/
│   ├── api/               # BFF route handlers
│   │   ├── auth/logout
│   │   └── chat/{sessions, stream, [id]/messages}
│   ├── layout.tsx
│   ├── page.tsx           # redirect → /chat or /login
│   └── globals.css
├── components/
│   ├── ui/                # Button, Input, Card, Alert
│   └── chat/              # ChatView, SessionSidebar, MessageView
├── lib/
│   ├── api/               # FastAPI client (server-only)
│   │   ├── client.ts      # base fetch + ApiError
│   │   ├── auth.ts        # /auth endpoints
│   │   ├── chat.ts        # /chat endpoints + SSE parser
│   │   └── knowledge.ts   # /knowledge endpoints
│   ├── session.ts         # Cookie session — get/set/clear, auto-refresh
│   ├── sse-client.ts      # Browser SSE parser
│   ├── env.ts             # Env var loader
│   └── utils.ts           # cn(), formatRelative()
└── proxy.ts               # Route protection (Next.js 16 proxy)
```

## Environment

| Var                     | Description                         | Default                 |
| ----------------------- | ----------------------------------- | ----------------------- |
| `RAG_API_URL`           | FastAPI base URL (server-side only) | `http://localhost:8000` |
| `SESSION_COOKIE_NAME`   | Cookie name                         | `rag_session`           |
| `SESSION_COOKIE_DOMAIN` | Cookie domain                       | (current host)          |
| `SESSION_COOKIE_SECURE` | `true` in production (HTTPS)        | `false`                 |

## Auth flow

1. User submits credentials → **Server Action** → `POST /auth/login` on FastAPI
2. FastAPI returns `TokenPair` (access + refresh JWTs)
3. Server Action stores the pair in a base64-encoded HttpOnly cookie
4. Subsequent requests: BFF route reads cookie → extracts access token →
   forwards as `Authorization: Bearer` to FastAPI
5. Expired access tokens are silently refreshed via the refresh token

Email-code verification UI is in place; the backend endpoint
(`/auth/code/send`) is planned per
[`../docs/backend/AUTH_DESIGN.md`](../docs/backend/AUTH_DESIGN.md). The form gracefully
degrades when the endpoint isn't available.

## Chat streaming

Browser opens `POST /api/chat/stream` (BFF route). The handler:

1. Validates session via cookie
2. Opens an SSE stream to FastAPI's `/chat/stream` with Bearer auth
3. Pipes the upstream body straight through to the browser

The client component parses SSE frames (`event:` + `data:`) into typed
`StreamEvent` objects (`token`, `tool_call`, `tool_result`, `retrieval`,
`done`, `error`) and incrementally updates the message state.

`AbortController` lets the user stop generation; cancellation propagates
up to FastAPI via the SSE connection close.
