import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/register"];
const PUBLIC_PREFIXES = [
  "/_next",
  "/favicon",
  "/public",
  "/api/health",
  // Auth helpers — must be reachable while logged-out / with a stale cookie
  // so we don't trap users in a redirect loop. The refresh-and-back bridge
  // is the most important entry point here: a Server Component bounces a
  // request with an expired access cookie through this prefix to rotate
  // the cookies before re-rendering.
  "/api/auth",
  // Per-Q&A shares are public by design — viewers don't need to log in.
  // The owner-only sub-routes (POST/DELETE) guard themselves at the BFF
  // layer via ``withAuth``, so it's safe to skip the proxy gate here.
  "/share",
  "/api/shares",
];

// Cookie names — kept in sync with ``lib/auth/session.server.ts``.
// We could derive these from env, but the names are stable enough that
// hardcoding keeps the middleware bundle tiny (middleware runs on every
// request — pulling in env utilities adds noticeable startup cost).
const ACCESS_COOKIE = "rag_at";
const REFRESH_COOKIE = "rag_rt";
const LEGACY_COMBINED_COOKIE = process.env.SESSION_COOKIE_NAME || "rag_session";

/**
 * Decode the base64url-encoded access-cookie envelope written by
 * ``setSession``. Returns the embedded **refresh** expiry (epoch
 * seconds) or 0 when the envelope is malformed / missing.
 *
 * We deliberately key off ``refresh_exp`` rather than ``access_exp``
 * here: the middleware just wants to know "is the session still
 * recoverable", and the refresh window is the answer to that. An
 * expired access JWT is fine — the SC layer handles that via
 * ``/api/auth/refresh-and-back``.
 *
 * Must stay in sync with the ``AccessCookiePayload`` shape in
 * ``lib/auth/session.server.ts``.
 */
function refreshExpFromAccessCookie(raw: string | undefined): number {
  if (!raw) return 0;
  try {
    let b64 = raw.replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    const payload = JSON.parse(atob(b64)) as {
      access_token?: string;
      refresh_exp?: number;
    };
    if (!payload.access_token || typeof payload.refresh_exp !== "number") {
      return 0;
    }
    return payload.refresh_exp;
  } catch {
    return 0;
  }
}

/**
 * The middleware's only job is to decide "should this request reach a
 * route at all", not "is the access token still valid".
 *
 * We can NOT inspect the refresh cookie here: it is scoped to
 * ``Path=/api/auth`` so the browser doesn't send it on regular page
 * navigations — that's the whole point of the refresh cookie's narrow
 * path. So we look at the access cookie instead, but only to confirm
 * the user has *some* session at all. An expired access (still inside
 * the cookie's max-age window, which we tie to the refresh expiry) is
 * fine: the Server Component will detect that and bounce through
 * ``/api/auth/refresh-and-back`` to rotate cookies. The middleware
 * only kicks the user to /login when even the access cookie is gone
 * (or its envelope's ``exp`` is so far in the past that it's outside
 * the refresh window — at which point refresh-and-back would fail too).
 *
 * Falls back to the legacy P-AUTH-1 combined cookie so a rolling
 * deploy doesn't kick everyone out the moment the new code lands.
 */
function hasValidSession(req: NextRequest): boolean {
  // Access cookie is the source of truth for "session exists" — its
  // ``Path=/`` means middleware sees it on every navigation. The
  // envelope carries the refresh window's expiry, so we can tell
  // "fully signed out" from "expired access but recoverable" without
  // ever needing to read the refresh cookie itself.
  const accessRaw = req.cookies.get(ACCESS_COOKIE)?.value;
  if (accessRaw) {
    const refreshExp = refreshExpFromAccessCookie(accessRaw);
    if (refreshExp > Math.floor(Date.now() / 1000)) {
      return true;
    }
  }

  // ---- legacy fallback (P-AUTH-1 single-cookie format) ----
  const legacy = req.cookies.get(LEGACY_COMBINED_COOKIE)?.value;
  if (!legacy) return false;
  try {
    let b64 = legacy.replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    const session = JSON.parse(atob(b64)) as { refresh_expires_at?: number };
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
    // Clear any stale cookies so this redirect is a clean reset. We
    // don't know each cookie's original ``Path`` here, so we re-emit
    // them with the same paths used when they were written.
    if (req.cookies.has(REFRESH_COOKIE)) {
      res.cookies.set({
        name: REFRESH_COOKIE,
        value: "",
        path: "/api",
        maxAge: 0,
      });
    }
    if (req.cookies.has("rag_at")) {
      res.cookies.set({ name: "rag_at", value: "", path: "/", maxAge: 0 });
    }
    if (req.cookies.has(LEGACY_COMBINED_COOKIE)) {
      res.cookies.set({
        name: LEGACY_COMBINED_COOKIE,
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
