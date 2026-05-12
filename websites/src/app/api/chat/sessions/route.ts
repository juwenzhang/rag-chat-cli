import { NextResponse } from "next/server";

import { chatApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { getAccessTokenWithRefresh } from "@/lib/session";

export async function GET() {
  const token = await getAccessTokenWithRefresh();
  if (!token)
    return NextResponse.json({ error: "UNAUTHENTICATED" }, { status: 401 });
  try {
    const items = await chatApi.listSessions(token);
    return NextResponse.json({ items });
  } catch (err) {
    if (err instanceof ApiError)
      return NextResponse.json(
        { error: err.code, message: err.message },
        { status: err.status }
      );
    return NextResponse.json({ error: "UPSTREAM_ERROR" }, { status: 502 });
  }
}

export async function POST(req: Request) {
  const token = await getAccessTokenWithRefresh();
  if (!token)
    return NextResponse.json({ error: "UNAUTHENTICATED" }, { status: 401 });

  let title: string | undefined;
  try {
    const body = (await req.json().catch(() => ({}))) as { title?: string };
    title = body?.title;
  } catch {
    /* noop */
  }

  try {
    const meta = await chatApi.createSession(token, title);
    return NextResponse.json(meta);
  } catch (err) {
    if (err instanceof ApiError)
      return NextResponse.json(
        { error: err.code, message: err.message },
        { status: err.status }
      );
    return NextResponse.json({ error: "UPSTREAM_ERROR" }, { status: 502 });
  }
}
