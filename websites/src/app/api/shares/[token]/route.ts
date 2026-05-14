import { NextResponse } from "next/server";

import { shareApi } from "@/lib/api";

import { bffErrorFrom, withAuth } from "../../_bff";

/** Public — no auth header. Anyone with the token can read the share. */
export async function GET(
  _req: Request,
  ctx: { params: Promise<{ token: string }> }
) {
  const { token: shareToken } = await ctx.params;
  try {
    return NextResponse.json(await shareApi.fetchSharePublic(shareToken));
  } catch (err) {
    return bffErrorFrom(err);
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
