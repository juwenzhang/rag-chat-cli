import { wikiApi } from "@/lib/api";

import { withAuth } from "../../../_bff";

export async function POST(
  _req: Request,
  ctx: { params: Promise<{ pageId: string }> }
) {
  const { pageId } = await ctx.params;
  return withAuth((token) => wikiApi.createPageShare(token, pageId));
}

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ pageId: string }> }
) {
  const { pageId } = await ctx.params;
  return withAuth((token) => wikiApi.getPageShare(token, pageId));
}
