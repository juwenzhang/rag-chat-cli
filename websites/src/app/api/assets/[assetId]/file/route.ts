import { NextResponse } from "next/server";

import { assetApi } from "@/lib/api";

import { withAuthResponse } from "../../../_bff";

export async function GET(_req: Request, ctx: { params: Promise<{ assetId: string }> }) {
  const { assetId } = await ctx.params;
  return withAuthResponse(async (token) => {
    const url = await assetApi.getImageDownloadUrl(token, assetId);
    return NextResponse.redirect(url, 307);
  });
}
