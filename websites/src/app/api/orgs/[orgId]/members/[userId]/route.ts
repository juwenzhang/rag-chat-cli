import { orgApi } from "@/lib/api";
import type { UpdateMemberRoleBody } from "@/lib/api/orgs";

import { readJson, withAuth } from "../../../../_bff";

interface Ctx {
  params: Promise<{ orgId: string; userId: string }>;
}

export async function PATCH(req: Request, { params }: Ctx) {
  const { orgId, userId } = await params;
  const body = await readJson<UpdateMemberRoleBody>(req);
  return withAuth((token) => orgApi.updateMember(token, orgId, userId, body));
}

export async function DELETE(_req: Request, { params }: Ctx) {
  const { orgId, userId } = await params;
  return withAuth(async (token) => {
    await orgApi.removeMember(token, orgId, userId);
    return { ok: true };
  });
}
