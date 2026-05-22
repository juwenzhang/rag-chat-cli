import "server-only";

import { headers as nextHeaders } from "next/headers";
import { NextResponse } from "next/server";

import { createRequestId, debugServer, type ApiDebugMeta } from "@/lib/api/shared/debug";
import { ApiError } from "@/lib/api/shared/types";
import { getAccessTokenWithRefresh } from "@/lib/auth/session.server";

export interface BffError {
  error: string;
  message: string;
  details?: unknown;
  requestId?: string;
  debug?: ApiDebugMeta;
}

export interface BffContext {
  requestId: string;
}

const SSE_HEADERS = {
  "Content-Type": "text/event-stream",
  "Cache-Control": "no-cache, no-transform",
  "X-Accel-Buffering": "no",
  Connection: "keep-alive",
} as const;

async function requestIdFromHeaders(): Promise<string> {
  try {
    return (await nextHeaders()).get("x-request-id") ?? createRequestId();
  } catch {
    return createRequestId();
  }
}

function withRequestId<T extends Response>(res: T, requestId: string): T {
  res.headers.set("x-request-id", requestId);
  return res;
}

export function bffError(
  code: string,
  message: string,
  status: number,
  details?: unknown,
  debug?: ApiDebugMeta
): NextResponse {
  const requestId = debug?.requestId;
  const body: BffError = { error: code, message };
  if (details !== undefined) body.details = details;
  if (requestId) body.requestId = requestId;
  if (process.env.NODE_ENV === "development" && debug) body.debug = debug;
  const res = NextResponse.json(body, { status });
  if (requestId) res.headers.set("x-request-id", requestId);
  return res;
}

export function bffErrorFrom(err: unknown, debug: ApiDebugMeta = {}): NextResponse {
  if (err instanceof ApiError) {
    const mergedDebug = { ...debug, ...err.debug };
    return bffError(err.code, err.message, err.status, err.details, mergedDebug);
  }
  return bffError("UPSTREAM_ERROR", (err as Error).message, 502, undefined, debug);
}

export async function withAuth<T>(
  inner: (token: string, ctx: BffContext) => Promise<T>
): Promise<NextResponse> {
  const requestId = await requestIdFromHeaders();
  const startedAt = performance.now();
  const token = await getAccessTokenWithRefresh();
  if (!token) {
    return bffError("UNAUTHENTICATED", "Session expired or missing.", 401, undefined, {
      requestId,
    });
  }
  try {
    const data = await inner(token, { requestId });
    const durationMs = Math.round(performance.now() - startedAt);
    debugServer(`[bff] ${requestId} 200 ${durationMs}ms`, { requestId, durationMs });
    return withRequestId(NextResponse.json(data), requestId);
  } catch (err) {
    const durationMs = Math.round(performance.now() - startedAt);
    return bffErrorFrom(err, { requestId, durationMs });
  }
}

export async function withAuthStream(
  inner: (token: string, ctx: BffContext) => Promise<Response>
): Promise<Response> {
  const requestId = await requestIdFromHeaders();
  const startedAt = performance.now();
  const token = await getAccessTokenWithRefresh();
  if (!token) {
    return bffError("UNAUTHENTICATED", "Session expired or missing.", 401, undefined, {
      requestId,
    });
  }
  try {
    const upstream = await inner(token, { requestId });
    const durationMs = Math.round(performance.now() - startedAt);
    debugServer(`[bff:stream] ${requestId} 200 ${durationMs}ms`, {
      requestId,
      durationMs,
    });
    return new Response(upstream.body, {
      status: 200,
      headers: { ...SSE_HEADERS, "x-request-id": requestId },
    });
  } catch (err) {
    const durationMs = Math.round(performance.now() - startedAt);
    return bffErrorFrom(err, { requestId, durationMs });
  }
}

export async function readJson<T>(req: Request): Promise<T> {
  try {
    return (await req.json()) as T;
  } catch {
    return {} as T;
  }
}
