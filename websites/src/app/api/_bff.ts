import "server-only";

import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/types";
import { getAccessTokenWithRefresh } from "@/lib/session";

/**
 * The single error envelope every BFF route emits. The browser-side API
 * client (`src/lib/api/browser`) parses exactly this shape back into an
 * `ApiError`, so the two sides stay in lockstep — change one, change both.
 *
 *   { error: "PROVIDER_NOT_FOUND", message: "…", details?: … }
 *
 * `error` is always a stable, machine-readable CODE (never a human
 * sentence); `message` is the human-readable text.
 */
export interface BffError {
  error: string;
  message: string;
  details?: unknown;
}

/** SSE passthrough headers — shared by every streaming route. */
const SSE_HEADERS = {
  "Content-Type": "text/event-stream",
  "Cache-Control": "no-cache, no-transform",
  "X-Accel-Buffering": "no",
  Connection: "keep-alive",
} as const;

/** Emit the standard error envelope with an explicit status. */
export function bffError(
  code: string,
  message: string,
  status: number,
  details?: unknown
): NextResponse {
  const body: BffError = { error: code, message };
  if (details !== undefined) body.details = details;
  return NextResponse.json(body, { status });
}

/**
 * Map an unknown thrown value onto the standard error envelope. Exported
 * for the few routes that can't use `withAuth` (e.g. public, unauthed
 * endpoints) but still want a consistent error shape.
 */
export function bffErrorFrom(err: unknown): NextResponse {
  if (err instanceof ApiError) {
    return bffError(err.code, err.message, err.status, err.details);
  }
  return bffError("UPSTREAM_ERROR", (err as Error).message, 502);
}

/**
 * Common BFF response shaper for JSON routes. Refreshes the session,
 * runs `inner(token)`, and converts upstream `ApiError` into the standard
 * envelope so route handlers can stay focused on the happy path.
 *
 * Success convention: the resolved value is returned verbatim as JSON —
 * list routes resolve to arrays, detail routes to objects, action-only
 * routes to `{ ok: true }`.
 */
export async function withAuth<T>(
  inner: (token: string) => Promise<T>
): Promise<NextResponse> {
  const token = await getAccessTokenWithRefresh();
  if (!token) {
    return bffError("UNAUTHENTICATED", "Session expired or missing.", 401);
  }
  try {
    return NextResponse.json(await inner(token));
  } catch (err) {
    return bffErrorFrom(err);
  }
}

/**
 * Streaming sibling of `withAuth`. `inner` returns the raw upstream
 * `Response` (an open SSE stream from FastAPI); on success its body is
 * piped straight through to the browser with SSE headers. Auth failures
 * and upstream `ApiError`s still come back as the JSON error envelope —
 * the browser client checks the content-type to tell them apart.
 */
export async function withAuthStream(
  inner: (token: string) => Promise<Response>
): Promise<Response> {
  const token = await getAccessTokenWithRefresh();
  if (!token) {
    return bffError("UNAUTHENTICATED", "Session expired or missing.", 401);
  }
  try {
    const upstream = await inner(token);
    return new Response(upstream.body, { status: 200, headers: SSE_HEADERS });
  } catch (err) {
    return bffErrorFrom(err);
  }
}

/** Parse a JSON request body, tolerating an empty/invalid body as `{}`. */
export async function readJson<T>(req: Request): Promise<T> {
  try {
    return (await req.json()) as T;
  } catch {
    return {} as T;
  }
}
