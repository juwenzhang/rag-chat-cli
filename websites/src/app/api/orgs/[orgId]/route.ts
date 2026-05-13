import { orgApi } from "@/lib/api";
import type { UpdateOrgBody } from "@/lib/api/orgs";

import { readJson, withAuth } from "../../_bff";

interface Ctx {
  params: Promise<{ orgId: string }>;
}

export async function GET(_req: Request, { params }: Ctx) {
  const { orgId } = await params;
  return withAuth((token) => orgApi.getOrg(token, orgId));
}

export async function PATCH(req: Request, { params }: Ctx) {
  const { orgId } = await params;
  const body = await readJson<UpdateOrgBody>(req);
  return withAuth((token) => orgApi.updateOrg(token, orgId, body));
}

export async function DELETE(_req: Request, { params }: Ctx) {
  const { orgId } = await params;
  return withAuth(async (token) => {
    await orgApi.deleteOrg(token, orgId);
    return { ok: true };
  });
}
