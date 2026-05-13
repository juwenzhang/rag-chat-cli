import { orgApi } from "@/lib/api";
import type { AddMemberBody } from "@/lib/api/orgs";

import { readJson, withAuth } from "../../../_bff";

interface Ctx {
  params: Promise<{ orgId: string }>;
}

export async function GET(_req: Request, { params }: Ctx) {
  const { orgId } = await params;
  return withAuth((token) => orgApi.listMembers(token, orgId));
}

export async function POST(req: Request, { params }: Ctx) {
  const { orgId } = await params;
  const body = await readJson<AddMemberBody>(req);
  return withAuth((token) => orgApi.addMember(token, orgId, body));
}
