/** Server-side HTTP client for the FastAPI backend. */

import "server-only";

import { headers as nextHeaders } from "next/headers";

import {
  createRequestId,
  debugServer,
  sanitizeForDebug,
  type ApiDebugMeta,
} from "@/lib/api/shared/debug";
import { ApiError } from "@/lib/api/shared/types";
import { env } from "@/lib/env";

export interface FetchOptions extends Omit<RequestInit, "body"> {
  /** Bearer access token; injected automatically by route handlers. */
  token?: string | null;
  /** Body — auto-serialised as JSON if it's a plain object. */
  body?: unknown;
  /** Query string params. */
  query?: Record<string, string | number | boolean | undefined>;
  /** Correlation id propagated from the BFF/browser request. */
  requestId?: string;
}

function buildUrl(path: string, query?: FetchOptions["query"]): string {
  const url = new URL(path, env.RAG_API_URL);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined) continue;
      url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

async function incomingRequestId(): Promise<string | null> {
  try {
    return (await nextHeaders()).get("x-request-id");
  } catch {
    return null;
  }
}

async function parseBody(res: Response): Promise<unknown> {
  if (res.status === 204) return undefined;
  const ct = res.headers.get("content-type") || "";
  try {
    if (ct.includes("application/json")) return await res.json();
    return await res.text();
  } catch {
    return null;
  }
}

function parseError(res: Response, payload: unknown, debug: ApiDebugMeta): ApiError {
  const obj = (payload && typeof payload === "object" ? payload : {}) as Record<
    string,
    unknown
  >;
  const code = typeof obj.code === "string" ? obj.code : `HTTP_${res.status}`;
  const message =
    typeof obj.detail === "string"
      ? obj.detail
      : typeof obj.message === "string"
        ? obj.message
        : res.statusText || "Request failed";
  return new ApiError(res.status, code, message, payload, debug);
}

export async function apiFetch<T = unknown>(
  path: string,
  opts: FetchOptions = {}
): Promise<T> {
  const { token, body, query, headers, requestId, ...rest } = opts;
  const rid = requestId ?? (await incomingRequestId()) ?? createRequestId();
  const url = buildUrl(path, query);
  const method = rest.method ?? (body === undefined ? "GET" : "POST");
  const isFormData = body instanceof FormData;
  const init: RequestInit = {
    ...rest,
    headers: {
      Accept: "application/json",
      "x-request-id": rid,
      ...(body !== undefined && !isFormData
        ? { "Content-Type": "application/json" }
        : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers as Record<string, string>),
    },
    body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
    cache: "no-store",
  };

  const startedAt = performance.now();
  const res = await fetch(url, init);
  const durationMs = Math.round(performance.now() - startedAt);
  const payload = await parseBody(res);
  const debug: ApiDebugMeta = {
    requestId: rid,
    method,
    upstreamPath: url,
    upstreamStatus: res.status,
    upstreamDurationMs: durationMs,
  };

  debugServer(`[upstream] ${method} ${path} ${res.status} ${durationMs}ms`, {
    requestId: rid,
    request: { method, path: url, body: sanitizeForDebug(body) },
    response: payload,
  });

  if (!res.ok) throw parseError(res, payload, debug);
  return payload as T;
}

export async function apiStream(
  path: string,
  opts: FetchOptions = {}
): Promise<Response> {
  const { token, body, query, headers, requestId, ...rest } = opts;
  const rid = requestId ?? (await incomingRequestId()) ?? createRequestId();
  const url = buildUrl(path, query);
  const method = rest.method ?? "GET";
  const startedAt = performance.now();
  const res = await fetch(url, {
    ...rest,
    headers: {
      Accept: "text/event-stream",
      "x-request-id": rid,
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers as Record<string, string>),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  const durationMs = Math.round(performance.now() - startedAt);

  debugServer(`[upstream:stream] ${method} ${path} ${res.status} ${durationMs}ms`, {
    requestId: rid,
    request: { method, path: url, body: sanitizeForDebug(body) },
    response: res.ok ? "<event-stream>" : await res.clone().text(),
  });

  if (!res.ok) {
    const payload = await parseBody(res);
    throw parseError(res, payload, {
      requestId: rid,
      method,
      upstreamPath: url,
      upstreamStatus: res.status,
      upstreamDurationMs: durationMs,
    });
  }
  return res;
}
