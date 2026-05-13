import { wikiApi } from "@/lib/api";
import type { UpdateWikiPageBody } from "@/lib/api/wiki";

import { readJson, withAuth } from "../../_bff";

interface Ctx {
  params: Promise<{ pageId: string }>;
}

export async function GET(_req: Request, { params }: Ctx) {
  const { pageId } = await params;
  return withAuth((token) => wikiApi.getPage(token, pageId));
}

export async function PATCH(req: Request, { params }: Ctx) {
  const { pageId } = await params;
  const body = await readJson<UpdateWikiPageBody>(req);
  return withAuth((token) => wikiApi.updatePage(token, pageId, body));
}

export async function DELETE(_req: Request, { params }: Ctx) {
  const { pageId } = await params;
  return withAuth(async (token) => {
    await wikiApi.deletePage(token, pageId);
    return { ok: true };
  });
}
