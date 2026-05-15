import { NextResponse } from "next/server";

import { wikiApi } from "@/lib/api";

import { bffErrorFrom, withAuth } from "../../_bff";

/** Public — no auth header. Anyone with the token can read the shared page. */
export async function GET(
  _req: Request,
  ctx: { params: Promise<{ token: string }> }
) {
  const { token: shareToken } = await ctx.params;
  try {
    return NextResponse.json(
      await wikiApi.fetchPageSharePublic(shareToken)
    );
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
    await wikiApi.revokePageShare(token, shareToken);
    return { ok: true };
  });
}
