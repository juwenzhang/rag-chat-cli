import { wikiApi } from "@/lib/api";
import type { UpdateWikiMemberRoleBody } from "@/lib/api/wiki";

import { readJson, withAuth } from "../../../../_bff";

interface Ctx {
  params: Promise<{ wikiId: string; userId: string }>;
}

export async function PATCH(req: Request, { params }: Ctx) {
  const { wikiId, userId } = await params;
  const body = await readJson<UpdateWikiMemberRoleBody>(req);
  return withAuth((token) =>
    wikiApi.updateWikiMember(token, wikiId, userId, body)
  );
}

export async function DELETE(_req: Request, { params }: Ctx) {
  const { wikiId, userId } = await params;
  return withAuth(async (token) => {
    await wikiApi.removeWikiMember(token, wikiId, userId);
    return { ok: true };
  });
}
