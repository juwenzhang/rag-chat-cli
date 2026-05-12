import { NextResponse, type NextRequest } from "next/server";

import { clearSession } from "@/lib/session";

/**
 * Safe escape hatch for Server Components that detect an invalid session.
 *
 * Server Components can't mutate cookies, so they can't simply call
 * `clearSession()` themselves. Instead they redirect here; this route
 * (a Route Handler — can write cookies) clears the cookie and bounces
 * the user to /login. Without this, a stale cookie + the proxy's
 * "logged-in users go to /chat" rule would create a redirect loop.
 */
export async function GET(req: NextRequest) {
  await clearSession();
  const next = req.nextUrl.searchParams.get("next");
  const url = new URL("/login", req.url);
  if (next && next.startsWith("/")) url.searchParams.set("next", next);
  return NextResponse.redirect(url);
}
