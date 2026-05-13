import { wikiApi } from "@/lib/api";
import type { CreateWikiBody } from "@/lib/api/wiki";

import { readJson, withAuth } from "../../../_bff";

interface Ctx {
  params: Promise<{ orgId: string }>;
}

export async function GET(_req: Request, { params }: Ctx) {
  const { orgId } = await params;
  return withAuth((token) => wikiApi.listWikis(token, orgId));
}

export async function POST(req: Request, { params }: Ctx) {
  const { orgId } = await params;
  const body = await readJson<CreateWikiBody>(req);
  return withAuth((token) => wikiApi.createWiki(token, orgId, body));
}
