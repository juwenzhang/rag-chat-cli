import { wikiApi } from "@/lib/api";
import type { AddWikiMemberBody } from "@/lib/api/wiki";

import { readJson, withAuth } from "../../../_bff";

interface Ctx {
  params: Promise<{ wikiId: string }>;
}

export async function GET(_req: Request, { params }: Ctx) {
  const { wikiId } = await params;
  return withAuth((token) => wikiApi.listWikiMembers(token, wikiId));
}

export async function POST(req: Request, { params }: Ctx) {
  const { wikiId } = await params;
  const body = await readJson<AddWikiMemberBody>(req);
  return withAuth((token) => wikiApi.addWikiMember(token, wikiId, body));
}
