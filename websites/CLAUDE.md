# Claude Frontend Rules

Read `AGENTS.md` first. The short version:

- This is a Next.js 16 SSR/BFF app; do not treat it like a simple CSR app.
- Follow the SSR MVC mapping in `src/features/README.md`.
- View components must not import `@/lib/api/browser`, `useRouter`, or `toast`.
- Put browser API calls in `features/*/services`.
- Put client orchestration in `features/*/hooks` or the page-level controller component.
- Keep `lib/api/browser`, `lib/api/server`, and `lib/api/shared` boundaries intact.
- Preserve request tracing (`x-request-id`, dev debug logs, sanitized debug payloads).
- Validate frontend changes with `pnpm lint` and `pnpm build` when possible.

Architecture reference: `../docs/FRONTEND_SSR_MVC.md`.
