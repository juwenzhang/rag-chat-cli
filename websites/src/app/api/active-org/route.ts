import { NextResponse } from "next/server";

import { setActiveOrg } from "@/lib/active-org";

import { bffError, readJson } from "../_bff";

/**
 * Switch the active workspace. This only touches a Next.js-side cookie
 * (no FastAPI call), so it doesn't go through `withAuth`.
 */
export async function POST(req: Request) {
  const { org_id } = await readJson<{ org_id?: string }>(req);
  if (!org_id) {
    return bffError("ORG_ID_REQUIRED", "org_id is required.", 400);
  }
  await setActiveOrg(org_id);
  return NextResponse.json({ ok: true, org_id });
}
