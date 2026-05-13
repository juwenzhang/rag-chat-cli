import { NextResponse } from "next/server";

import { shareApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";

import { withAuth } from "../../_bff";

/** Public — no auth header. Anyone with the token can read the share. */
export async function GET(
  _req: Request,
  ctx: { params: Promise<{ token: string }> }
) {
  const { token: shareToken } = await ctx.params;
  try {
    const data = await shareApi.fetchSharePublic(shareToken);
    return NextResponse.json(data);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json(
        { error: err.code, message: err.message },
        { status: err.status }
      );
    }
    return NextResponse.json(
      { error: "UPSTREAM_ERROR", message: (err as Error).message },
      { status: 502 }
    );
  }
}

export async function DELETE(
  _req: Request,
  ctx: { params: Promise<{ token: string }> }
) {
  const { token: shareToken } = await ctx.params;
  return withAuth(async (token) => {
    await shareApi.revokeShare(token, shareToken);
    return { ok: true };
  });
}
