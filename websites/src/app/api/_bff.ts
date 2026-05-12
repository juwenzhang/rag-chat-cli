import "server-only";

import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/types";
import { getAccessTokenWithRefresh } from "@/lib/session";

/**
 * Common BFF response shaper. Runs ``inner(token)`` after refreshing the
 * session and converts upstream :class:`ApiError` into a JSON envelope so
 * route handlers can stay focused on the happy path.
 */
export async function withAuth<T>(
  inner: (token: string) => Promise<T>
): Promise<NextResponse> {
  const token = await getAccessTokenWithRefresh();
  if (!token) {
    return NextResponse.json(
      { error: "UNAUTHENTICATED" },
      { status: 401 }
    );
  }
  try {
    const data = await inner(token);
    return NextResponse.json(data);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(
        { error: err.code, message: err.message, details: err.details },
        { status: err.status }
      );
    }
    return NextResponse.json(
      { error: "UPSTREAM_ERROR", message: (err as Error).message },
      { status: 502 }
    );
  }
}

export async function readJson<T>(req: Request): Promise<T> {
  try {
    return (await req.json()) as T;
  } catch {
    return {} as T;
  }
}
