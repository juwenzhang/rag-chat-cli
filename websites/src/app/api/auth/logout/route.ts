import { NextResponse } from "next/server";

import { authApi } from "@/lib/api";
import { clearSession, getSession } from "@/lib/session";

export async function POST() {
  const session = await getSession();
  if (session?.refresh_token) {
    try {
      await authApi.logout(session.refresh_token);
    } catch {
      // best-effort: clear local cookie even if backend revocation fails
    }
  }
  await clearSession();
  return NextResponse.json({ ok: true });
}
