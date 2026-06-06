import { NextResponse, type NextRequest } from "next/server";

import { clearSession, getAccessTokenWithRefresh } from "@/lib/auth/session.server";

/**
 * Bridge between Server Components and the cookie write surface.
 *
 * Server Components cannot mutate cookies, so when they detect an expired
 * access token (but the refresh is still valid) they cannot rotate the
 * session themselves. Instead they redirect here; this Route Handler
 * runs `getAccessTokenWithRefresh` (which writes the rotated cookie)
 * and then 302s the user back to the page they were trying to render.
 *
 * Failure modes:
 *   - refresh expired / revoked / network error → clearSession() and
 *     fall through to /login (with optional ?next= preserved).
 *
 * The ``next`` query parameter is validated to be a same-origin path so
 * the endpoint cannot be abused as an open redirect.
 */
function isSafeNext(value: string | null): value is string {
  if (!value) return false;
  if (!value.startsWith("/")) return false;
  if (value.startsWith("//")) return false; // protocol-relative URL
  // Never bounce back into auth helpers — that would form a loop with
  // the very Server Component that redirected us here.
  if (value.startsWith("/api/auth")) return false;
  return true;
}

export async function GET(req: NextRequest) {
  const rawNext = req.nextUrl.searchParams.get("next");
  const safeNext = isSafeNext(rawNext) ? rawNext : "/chat";

  try {
    const token = await getAccessTokenWithRefresh();
    if (token) {
      return NextResponse.redirect(new URL(safeNext, req.url));
    }
  } catch {
    // fall through to login
  }

  await clearSession();
  const loginUrl = new URL("/login", req.url);
  if (isSafeNext(rawNext)) {
    loginUrl.searchParams.set("next", rawNext);
  }
  return NextResponse.redirect(loginUrl);
}
