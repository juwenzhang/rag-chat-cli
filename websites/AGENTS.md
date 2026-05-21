<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This project uses Next.js 16 / App Router / React 19. APIs, conventions, and file structure may differ from older training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing framework-sensitive code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# Web Frontend Agent Rules

本文档是面向 AI/人类协作者的前端约束。更完整的架构说明见：

- `src/features/README.md`
- `../docs/FRONTEND_SSR_MVC.md`
- `../docs/FRONTEND_NEXT_OPTIMIZATION.md`

## 1. Why these rules exist

This is an SSR/BFF application, not a simple CSR app. The runtime spans:

```text
Browser -> Client Component -> Next BFF Route Handler -> FastAPI
Server Component -> FastAPI
Zustand store / SSE stream / cookies
```

Without strict boundaries, logic quickly becomes hard to debug:

- View components call APIs directly.
- Server Components and Client Components fetch the same data independently.
- Route Handlers hide upstream errors.
- Stores mix UI side effects, navigation, and data state.
- SSR/CSR state ownership becomes unclear.

The project therefore uses a Next.js SSR version of MVC.

## 2. MVC mapping

```text
app/**                         Server Controller
features/*/hooks               Client Controller
features/*/services            Model Service
features/*/stores              Model State
features/*/components          View
components/ui                  Pure UI
components/shell               Global shell View/Controller boundary
lib/api/browser                Browser -> BFF client
lib/api/server                 Server/Route Handler -> FastAPI client
lib/api/shared                 Shared DTOs/debug metadata
```

## 3. Hard rules for View components

Files under `features/*/components` and `components/ui` should render UI and emit callbacks.

Do not import in View components:

```ts
import { api } from "@/lib/api/browser";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
```

Allowed in View components:

- local UI state: open/close, draft input, expanded/collapsed, selected tab.
- pure display derivation via `useMemo`.
- DOM/editor refs.
- `next/link` for declarative navigation.
- browser UI actions like copy-to-clipboard when they are not business orchestration.

If a component needs API/router/toast, create or use a controller hook or feature service.

View component size guidance:

- Target `150 ~ 220` lines per View file.
- If a View exceeds `250` lines, evaluate splitting.
- If a View exceeds `350` lines, split by default.
- Prefer extracting header, toolbar, list, row, dialog body, form fields, empty state, and footer actions.
- Extracted child Views must still be props-in/callbacks-out and must not import API/router/toast.

Component-family directory guidance:

- If a View family has more than 2 files, create a same-name directory.
- Keep a stable `index.ts` export in that directory.
- Keep parts/helpers beside the main component, not scattered in `components/` root.
- `components/` root should contain page-level entries, small single-file Views, or shared Views only.

## 4. Controller rules

Client controllers live in `features/*/hooks` or a page-level client component temporarily acting as controller.

Controllers may:

- call `features/*/services`.
- call `features/*/stores`.
- use `useRouter`.
- call `toast`.
- orchestrate autosave, SSE, optimistic update, conflict recovery, redirects.

Controllers should not contain large JSX trees. If JSX grows, split a View component.

## 5. Service rules

Services live in `features/*/services` and are the only feature layer that should call `@/lib/api/browser`.

Services may:

- call browser API client.
- adapt request/response shapes.
- compose small API use cases.

Services must not:

- import React.
- use `toast`.
- use `router`.
- mutate UI state.

## 6. Store rules

Stores live in `features/*/stores` or `src/stores`.

Use stores for cross-component state only:

- chat transcript / stream state.
- active shell user/org state.
- wiki sidebar title overrides.
- provider page state.

Do not create stores for one local form/dialog. Strict MVC preference: stores should not call `toast` or `router`; move those side effects into controllers when touching old code.

## 7. API boundary rules

- Browser-side feature code uses `@/lib/api/browser` only through `features/*/services`.
- Server Components / Route Handlers use `@/lib/api` or `@/lib/api/server/*`.
- Shared DTOs use `@/lib/api/shared/types`.
- Request debug utilities live in `@/lib/api/shared/debug`.
- Do not import `server-only` modules into Client Components.

## 8. Request observability rules

The API clients propagate `x-request-id` and log dev-only request traces.

When debugging network problems, check:

1. Browser console `[api] ...` logs.
2. Next server terminal `[upstream] ...` logs.
3. `ApiError.debug` metadata.
4. BFF response `debug` field in development.

Do not remove request-id propagation or debug sanitization.

## 9. Before changing frontend architecture

Before adding new folders or abstractions:

1. Check `src/features/README.md`.
2. Prefer existing `components/hooks/services/stores` mapping.
3. Do not add `containers/` unless a module genuinely needs it.
4. Run:

```bash
pnpm lint
pnpm build
```

Current known lint warning: `src/components/ui/virtual-table.tsx` has a TanStack Virtual / React Compiler warning; it is non-blocking.
