import { wikiApi } from "@/lib/api";
import type { CreateWikiPageBody } from "@/lib/api/wiki";

import { readJson, withAuth } from "../../../_bff";

interface Ctx {
  params: Promise<{ wikiId: string }>;
}

export async function GET(_req: Request, { params }: Ctx) {
  const { wikiId } = await params;
  return withAuth((token) => wikiApi.listPages(token, wikiId));
}

export async function POST(req: Request, { params }: Ctx) {
  const { wikiId } = await params;
  const body = await readJson<CreateWikiPageBody>(req);
  return withAuth((token) => wikiApi.createPage(token, wikiId, body));
}
