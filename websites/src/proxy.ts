import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/register"];
const PUBLIC_PREFIXES = [
  "/_next",
  "/favicon",
  "/public",
  "/api/health",
  // Auth helpers — must be reachable while logged-out / with a stale cookie
  // so we don't trap users in a redirect loop.
  "/api/auth",
  // Per-Q&A shares are public by design — viewers don't need to log in.
  // The owner-only sub-routes (POST/DELETE) guard themselves at the BFF
  // layer via ``withAuth``, so it's safe to skip the proxy gate here.
  "/share",
  "/api/shares",
];

const SESSION_COOKIE = process.env.SESSION_COOKIE_NAME || "rag_session";

/**
 * Decode the base64url-encoded session cookie and check whether the
 * refresh token is still valid. We don't check the access token here —
 * an expired access with a valid refresh is still a "logged-in" state
 * because BFF route handlers will rotate it on the next API call.
 *
 * Returns false on missing cookie, malformed payload, or expired refresh.
 */
function hasValidSession(req: NextRequest): boolean {
  const raw = req.cookies.get(SESSION_COOKIE)?.value;
  if (!raw) return false;
  try {
    let b64 = raw.replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    const decoded = atob(b64);
    const session = JSON.parse(decoded) as { refresh_expires_at?: number };
    const exp = Number(session.refresh_expires_at) || 0;
    return exp > Math.floor(Date.now() / 1000);
  } catch {
    return false;
  }
}

export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Forward the current pathname as a request header so server
  // components can read it (Next 16 strips the URL from
  // RouteSegmentConfig). Used by /wiki/layout to derive the active
  // wiki id from the URL while staying a server component.
  const requestHeaders = new Headers(req.headers);
  requestHeaders.set("x-pathname", pathname);

  for (const p of PUBLIC_PREFIXES) {
    if (pathname.startsWith(p)) {
      return NextResponse.next({ request: { headers: requestHeaders } });
    }
  }

  const validSession = hasValidSession(req);
  const isPublic = PUBLIC_PATHS.includes(pathname);

  // Logged-in user visiting /login or /register → bounce to chat
  if (isPublic && validSession) {
    return NextResponse.redirect(new URL("/chat", req.url));
  }

  // Anonymous (or stale-cookie) user hitting a protected route → bounce
  // to login. Stale cookies are cleared here so the next request comes
  // in clean.
  if (!isPublic && !validSession && pathname !== "/") {
    const res = NextResponse.redirect(
      (() => {
        const url = new URL("/login", req.url);
        url.searchParams.set("next", pathname);
        return url;
      })()
    );
    // Clear any stale cookie so this redirect is a clean reset.
    if (req.cookies.has(SESSION_COOKIE)) {
      res.cookies.set({
        name: SESSION_COOKIE,
        value: "",
        path: "/",
        maxAge: 0,
      });
    }
    return res;
  }

  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.svg).*)"],
};
