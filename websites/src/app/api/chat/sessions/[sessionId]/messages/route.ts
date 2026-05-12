import { NextResponse } from "next/server";

import { chatApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { getAccessTokenWithRefresh } from "@/lib/session";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ sessionId: string }> }
) {
  const token = await getAccessTokenWithRefresh();
  if (!token)
    return NextResponse.json({ error: "UNAUTHENTICATED" }, { status: 401 });

  const { sessionId } = await ctx.params;
  try {
    const items = await chatApi.getMessages(token, sessionId);
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
