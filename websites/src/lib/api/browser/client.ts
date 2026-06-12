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

import {
  createRequestId,
  debugGroup,
  sanitizeForDebug,
  type ApiDebugMeta,
} from "@/lib/api/shared/debug";
import { ApiError } from "@/lib/api/shared/types";

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

function buildInit(opts: BffRequestOptions, requestId: string): RequestInit {
  const { body, headers, ...rest } = opts;
  return {
    cache: "no-store",
    ...rest,
    headers: {
      Accept: "application/json",
      "x-request-id": requestId,
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(headers as Record<string, string>),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  };
}

async function parseBody(res: Response): Promise<unknown> {
  if (res.status === 204) return undefined;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return await res.json();
  return await res.text();
}

function debugFromPayload(payload: unknown): ApiDebugMeta | undefined {
  if (!payload || typeof payload !== "object") return undefined;
  const debug = (payload as Record<string, unknown>).debug;
  return debug && typeof debug === "object" ? (debug as ApiDebugMeta) : undefined;
}

/** Turn a non-2xx BFF response into an `ApiError`. */
function toApiError(
  res: Response,
  payload: unknown,
  fallbackDebug: ApiDebugMeta
): ApiError {
  const obj = (payload && typeof payload === "object" ? payload : {}) as Record<
    string,
    unknown
  >;
  const code = typeof obj.error === "string" ? obj.error : `HTTP_${res.status}`;
  const message =
    typeof obj.message === "string" ? obj.message : res.statusText || "Request failed";
  return new ApiError(res.status, code, message, obj.details, {
    ...fallbackDebug,
    ...debugFromPayload(payload),
  });
}

export async function bff<T = unknown>(
  path: string,
  opts: BffRequestOptions = {}
): Promise<T> {
  const requestId = createRequestId();
  const url = withQuery(path, opts.query);
  const method = opts.method ?? (opts.body === undefined ? "GET" : "POST");
  const startedAt = performance.now();
  const res = await fetch(url, buildInit(opts, requestId));
  const durationMs = Math.round(performance.now() - startedAt);
  const responseRequestId = res.headers.get("x-request-id") ?? requestId;
  const payload = await parseBody(res);
  const meta: ApiDebugMeta = {
    requestId: responseRequestId,
    method,
    path: url,
    status: res.status,
    durationMs,
  };

  debugGroup(`[api] ${method} ${url} ${res.status} ${durationMs}ms`, {
    requestId: responseRequestId,
    request: { method, path: url, body: sanitizeForDebug(opts.body) },
    response: payload,
  });

  if (!res.ok) throw toApiError(res, payload, meta);
  return payload as T;
}

export async function bffForm<T = unknown>(
  path: string,
  formData: FormData,
  opts: { signal?: AbortSignal } = {}
): Promise<T> {
  const requestId = createRequestId();
  const startedAt = performance.now();
  const res = await fetch(path, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "x-request-id": requestId,
    },
    body: formData,
    credentials: "same-origin",
    cache: "no-store",
    signal: opts.signal,
  });
  const durationMs = Math.round(performance.now() - startedAt);
  const responseRequestId = res.headers.get("x-request-id") ?? requestId;
  const payload = await parseBody(res);
  const meta: ApiDebugMeta = {
    requestId: responseRequestId,
    method: "POST",
    path,
    status: res.status,
    durationMs,
  };

  debugGroup(`[api] POST ${path} ${res.status} ${durationMs}ms`, {
    requestId: responseRequestId,
    request: { method: "POST", path, body: "<form-data>" },
    response: payload,
  });

  if (!res.ok) throw toApiError(res, payload, meta);
  return payload as T;
}

export async function bffStream(
  path: string,
  opts: BffRequestOptions = {}
): Promise<Response> {
  const requestId = createRequestId();
  const url = withQuery(path, opts.query);
  const method = opts.method ?? "GET";
  const init = buildInit(opts, requestId);
  const startedAt = performance.now();
  const res = await fetch(url, {
    ...init,
    headers: {
      ...(init.headers as Record<string, string>),
      Accept: "text/event-stream",
    },
  });
  const durationMs = Math.round(performance.now() - startedAt);
  const responseRequestId = res.headers.get("x-request-id") ?? requestId;

  debugGroup(`[api:stream] ${method} ${url} ${res.status} ${durationMs}ms`, {
    requestId: responseRequestId,
    request: { method, path: url, body: sanitizeForDebug(opts.body) },
    response: res.ok ? "<event-stream>" : await res.clone().text(),
  });

  if (!res.ok) {
    const payload = await parseBody(res);
    throw toApiError(res, payload, {
      requestId: responseRequestId,
      method,
      path: url,
      status: res.status,
      durationMs,
    });
  }
  return res;
}
