import { NextResponse } from "next/server";

import { providerApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { getAccessTokenWithRefresh } from "@/lib/session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface PullBody {
  model?: string;
}

export async function POST(
  req: Request,
  ctx: { params: Promise<{ providerId: string }> }
) {
  const token = await getAccessTokenWithRefresh();
  if (!token) {
    return NextResponse.json({ error: "UNAUTHENTICATED" }, { status: 401 });
  }

  const { providerId } = await ctx.params;

  let body: PullBody;
  try {
    body = (await req.json()) as PullBody;
  } catch {
    return NextResponse.json({ error: "INVALID_JSON" }, { status: 400 });
  }
  if (!body.model || typeof body.model !== "string") {
    return NextResponse.json({ error: "MISSING_MODEL" }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await providerApi.openPullModelStream(token, providerId, {
      model: body.model,
    });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(
        { error: err.code, message: err.message },
        { status: err.status }
      );
    }
    return NextResponse.json({ error: "UPSTREAM_ERROR" }, { status: 502 });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
      Connection: "keep-alive",
    },
  });
}
