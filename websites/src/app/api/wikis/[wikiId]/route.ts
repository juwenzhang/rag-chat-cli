import { wikiApi } from "@/lib/api";
import type { UpdateWikiBody } from "@/lib/api/wiki";

import { readJson, withAuth } from "../../_bff";

interface Ctx {
  params: Promise<{ wikiId: string }>;
}

export async function GET(_req: Request, { params }: Ctx) {
  const { wikiId } = await params;
  return withAuth((token) => wikiApi.getWiki(token, wikiId));
}

export async function PATCH(req: Request, { params }: Ctx) {
  const { wikiId } = await params;
  const body = await readJson<UpdateWikiBody>(req);
  return withAuth((token) => wikiApi.updateWiki(token, wikiId, body));
}

export async function DELETE(_req: Request, { params }: Ctx) {
  const { wikiId } = await params;
  return withAuth(async (token) => {
    await wikiApi.deleteWiki(token, wikiId);
    return { ok: true };
  });
}
