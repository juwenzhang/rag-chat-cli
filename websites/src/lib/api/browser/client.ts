/**
 * Browser-side API client for the BFF (`src/app/api/**`).
 *
 * Client Components never call `src/lib/api/*` (those are `server-only`)
 * and never hit FastAPI directly — they go through the Next.js Route
 * Handlers. This module is the typed counterpart to that hop: it knows
 * the BFF envelope (`src/app/api/_bff.ts`), so call sites get a parsed
 * payload or a thrown `ApiError` instead of hand-rolling `fetch` + `.json()`
 * + status checks everywhere.
 *
 * NOT `server-only` — this is the one `lib/api` module the browser imports.
 */

import { ApiError } from "@/lib/api/types";

export interface BffRequestOptions extends Omit<RequestInit, "body"> {
  /** Body — auto-serialised as JSON if it's a plain object. */
  body?: unknown;
  /** Query string params; `undefined` values are dropped. */
  query?: Record<string, string | number | boolean | undefined>;
}

function withQuery(path: string, query?: BffRequestOptions["query"]): string {
  if (!query) return path;
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined) usp.set(k, String(v));
  }
  const qs = usp.toString();
  return qs ? `${path}?${qs}` : path;
}

function buildInit(opts: BffRequestOptions): RequestInit {
  // `query` is consumed by `withQuery` before this runs; leaving it in
  // `rest` is harmless — `fetch` ignores unknown `RequestInit` keys.
  const { body, headers, ...rest } = opts;
  return {
    // Auth-bearing BFF responses must never be served from the HTTP
    // cache — a stale read could leak across sessions. Callers can still
    // override `cache` explicitly via `opts`.
    cache: "no-store",
    ...rest,
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(headers as Record<string, string>),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    // The session cookie is HttpOnly and same-origin; this keeps it
    // attached even when callers pass their own `RequestInit`.
    credentials: "same-origin",
  };
}

/**
 * Turn a non-2xx BFF response into an `ApiError`. The BFF always emits
 * `{ error: CODE, message, details? }` (see `_bff.ts`), but we stay
 * defensive in case a proxy or framework error page slips through.
 */
async function toApiError(res: Response): Promise<ApiError> {
  let payload: unknown = null;
  try {
    payload = await res.json();
  } catch {
    /* non-JSON body (e.g. an HTML error page) */
  }
  const obj = (payload && typeof payload === "object" ? payload : {}) as Record<
    string,
    unknown
  >;
  const code = typeof obj.error === "string" ? obj.error : `HTTP_${res.status}`;
  const message =
    typeof obj.message === "string"
      ? obj.message
      : res.statusText || "Request failed";
  return new ApiError(res.status, code, message, obj.details);
}

/**
 * Perform a JSON request against the BFF. Resolves to the parsed body
 * (or `undefined` for `204`), throws `ApiError` on any non-2xx response.
 */
export async function bff<T = unknown>(
  path: string,
  opts: BffRequestOptions = {}
): Promise<T> {
  const res = await fetch(withQuery(path, opts.query), buildInit(opts));

  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;

  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}

/**
 * Open a streaming request (SSE) against the BFF. Resolves to the raw
 * `Response` so the caller can consume `response.body` — see
 * `src/lib/sse-client.ts`. Auth/validation failures still arrive as the
 * JSON error envelope, so we surface those as a thrown `ApiError`.
 */
export async function bffStream(
  path: string,
  opts: BffRequestOptions = {}
): Promise<Response> {
  const init = buildInit(opts);
  const res = await fetch(withQuery(path, opts.query), {
    ...init,
    // Keep the JSON Content-Type from `buildInit` (POST streams carry a
    // JSON body) but ask for an event-stream back.
    headers: { ...(init.headers as Record<string, string>), Accept: "text/event-stream" },
  });
  if (!res.ok) throw await toApiError(res);
  return res;
}
