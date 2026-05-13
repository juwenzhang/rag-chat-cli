import { orgApi } from "@/lib/api";
import type { TransferOwnershipBody } from "@/lib/api/orgs";

import { readJson, withAuth } from "../../../_bff";

interface Ctx {
  params: Promise<{ orgId: string }>;
}

export async function POST(req: Request, { params }: Ctx) {
  const { orgId } = await params;
  const body = await readJson<TransferOwnershipBody>(req);
  return withAuth((token) => orgApi.transferOwnership(token, orgId, body));
}
