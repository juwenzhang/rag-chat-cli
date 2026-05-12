import { NextResponse } from "next/server";

import { chatApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { getAccessTokenWithRefresh } from "@/lib/session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface ChatStreamBody {
  session_id: string;
  content: string;
  use_rag?: boolean;
}

export async function POST(req: Request) {
  const token = await getAccessTokenWithRefresh();
  if (!token) {
    return NextResponse.json(
      { error: "UNAUTHENTICATED" },
      { status: 401 }
    );
  }

  let body: ChatStreamBody;
  try {
    body = (await req.json()) as ChatStreamBody;
  } catch {
    return NextResponse.json({ error: "INVALID_JSON" }, { status: 400 });
  }

  if (!body.session_id || !body.content) {
    return NextResponse.json(
      { error: "MISSING_FIELDS" },
      { status: 400 }
    );
  }

  let upstream: Response;
  try {
    upstream = await chatApi.openChatStream(token, body);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(
        { error: err.code, message: err.message },
        { status: err.status }
      );
    }
    return NextResponse.json({ error: "UPSTREAM_ERROR" }, { status: 502 });
  }

  // Forward the SSE stream straight through.
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
