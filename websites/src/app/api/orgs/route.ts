import { orgApi } from "@/lib/api";
import type { CreateOrgBody } from "@/lib/api/orgs";

import { readJson, withAuth } from "../_bff";

export async function GET() {
  return withAuth((token) => orgApi.listOrgs(token));
}

export async function POST(req: Request) {
  const body = await readJson<CreateOrgBody>(req);
  return withAuth((token) => orgApi.createOrg(token, body));
}
