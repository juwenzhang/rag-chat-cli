import { NextResponse } from "next/server";

import { setActiveOrg } from "@/lib/active-org";

interface Body {
  org_id?: string;
}

export async function POST(req: Request) {
  const body = (await req.json().catch(() => ({}))) as Body;
  if (!body.org_id) {
    return NextResponse.json({ error: "org_id required" }, { status: 400 });
  }
  await setActiveOrg(body.org_id);
  return NextResponse.json({ ok: true, org_id: body.org_id });
}
