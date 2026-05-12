/**
 * Server-side HTTP client for the FastAPI backend.
 *
 * This module is imported only from Server Components and Route Handlers
 * (the BFF layer). The browser never talks to FastAPI directly — it talks
 * to Next.js, which holds the session cookie, extracts the bearer token,
 * and forwards the request server-side.
 *
 * Rationale (docs/ROADMAP.md §2): keeping FastAPI off the public internet
 * lets us evolve the auth contract on the Next.js side (HttpOnly cookies,
 * email verification, CSRF) without breaking the FastAPI protocol that
 * the CLI also relies on.
 */

import "server-only";

import { env } from "@/lib/env";
import { ApiError } from "@/lib/api/types";

export interface FetchOptions extends Omit<RequestInit, "body"> {
  /** Bearer access token; injected automatically by route handlers. */
  token?: string | null;
  /** Body — auto-serialised as JSON if it's a plain object. */
  body?: unknown;
  /** Query string params. */
  query?: Record<string, string | number | boolean | undefined>;
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

async function parseError(res: Response): Promise<ApiError> {
  let payload: unknown = null;
  try {
    payload = await res.json();
  } catch {
    /* non-json body */
  }
  const obj = (payload && typeof payload === "object" ? payload : {}) as Record<
    string,
    unknown
  >;
  const code =
    typeof obj.code === "string" ? obj.code : `HTTP_${res.status}`;
  const message =
    typeof obj.detail === "string"
      ? obj.detail
      : typeof obj.message === "string"
        ? obj.message
        : res.statusText || "Request failed";
  return new ApiError(res.status, code, message, payload);
}

export async function apiFetch<T = unknown>(
  path: string,
  opts: FetchOptions = {}
): Promise<T> {
  const { token, body, query, headers, ...rest } = opts;

  const init: RequestInit = {
    ...rest,
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers as Record<string, string>),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    // Always opt out of Next's fetch cache — auth-bearing requests must not be cached.
    cache: "no-store",
  };

  const res = await fetch(buildUrl(path, query), init);

  if (!res.ok) {
    throw await parseError(res);
  }

  // 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }

  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}

/**
 * Open a raw response (no body parsing) — used for SSE streaming where the
 * caller wants to consume the body as a ReadableStream.
 */
export async function apiStream(
  path: string,
  opts: FetchOptions = {}
): Promise<Response> {
  const { token, body, query, headers, ...rest } = opts;

  const res = await fetch(buildUrl(path, query), {
    ...rest,
    headers: {
      Accept: "text/event-stream",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers as Record<string, string>),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });

  if (!res.ok) {
    throw await parseError(res);
  }
  return res;
}
