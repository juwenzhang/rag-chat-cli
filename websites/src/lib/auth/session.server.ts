/**
 * Server-side session management — double-cookie BFF model (P-AUTH-2).
 *
 * The browser carries two HttpOnly cookies:
 *
 *   - ``rag_at`` (``Path=/``)            → carries the **access** token,
 *                                          plus the refresh-window expiry
 *                                          so a Server Component can tell
 *                                          "expired access but recoverable"
 *                                          apart from "fully signed out"
 *                                          without ever needing to read
 *                                          ``rag_rt``.
 *
 *   - ``rag_rt`` (``Path=/api``)         → carries the **refresh** token.
 *                                          Restricted to ``/api`` so the
 *                                          browser never ships it on
 *                                          regular page navigation
 *                                          (``/chat``, ``/wiki``, …).
 *                                          BFF Route Handlers under
 *                                          ``/api/*`` *do* see it, which
 *                                          is what lets them silently
 *                                          rotate the session when an
 *                                          access token expires mid-
 *                                          interaction.
 *
 * The cookies are written by this BFF, **not** by the FastAPI backend.
 * The server-side ``set_session_cookies`` (``api/cookies.py``) is in
 * place for future scenarios where a browser request hits the backend
 * directly (OAuth callbacks land there in P-AUTH-3) but during P-AUTH-2
 * every cookie write goes through this module.
 *
 * Two surfaces, distinguished by write capability:
 *
 *   - ``getSession()``, ``getCurrentUser()``, ``getAccessToken()`` are
 *     READ-ONLY and safe to call from any context, including Server
 *     Components. They will *not* refresh an expired access token
 *     because cookies can only be mutated from Server Actions / Route
 *     Handlers. Because Server Components run on paths *outside*
 *     ``/api/auth``, they only see ``rag_at`` — that's why ``rag_at``'s
 *     envelope encodes the refresh-window expiry too.
 *
 *   - ``getAccessTokenWithRefresh()``, ``setSession()``, ``clearSession()``
 *     all WRITE the cookies. They must be called from a Server Action
 *     or Route Handler. Server Component code paths redirect to
 *     ``/api/auth/refresh-and-back`` to perform the rotation; see
 *     ``requireAccessToken`` below.
 */

import "server-only";

import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

import { env } from "@/lib/env";
import { authApi } from "@/lib/api";
import type { TokenPair, UserOut } from "@/lib/api/shared/types";

// Cookie names — kept as constants so a future config-driven rename is
// a one-line change. Names are aligned with the backend cookie names
// (``api/cookies.py``); the encoded payload differs (BFF uses an
// envelope with ``exp`` so we can decide expiry without parsing the
// JWT, the backend writes raw JWT tokens for direct-to-backend flows).
const ACCESS_COOKIE = "rag_at";
const REFRESH_COOKIE = "rag_rt";

// ``rag_rt`` is scoped to ``/api`` so the browser never sends it on
// regular page loads (``/chat``, ``/wiki``, …) — only BFF Route
// Handlers see it, which is what lets them silently rotate the
// session on expired-access requests. Server Components still cannot
// see it (they run on non-``/api`` paths) and therefore cannot bypass
// the ``refresh-and-back`` bridge.
const REFRESH_COOKIE_PATH = "/api";

const CLOCK_SKEW_S = 30;

// Legacy cookie name (P-AUTH-1) — read for compatibility during a
// rolling deploy, deleted on first session write.
const LEGACY_COMBINED_COOKIE_NAME = env.SESSION_COOKIE_NAME;

export interface Session {
  access_token: string;
  /**
   * The refresh token. May be ``null`` when read from a Server Component
   * because the refresh cookie's ``Path=/api/auth`` keeps it out of
   * sight on ordinary page loads. Use ``getAccessTokenWithRefresh``
   * (which runs in Route Handlers) when you actually need to call
   * ``/auth/refresh``.
   */
  refresh_token: string | null;
  access_expires_at: number; // epoch seconds
  refresh_expires_at: number;
}

/**
 * What we pack into the ``rag_at`` cookie. The access cookie is the
 * one Server Components see, so it has to carry **both** expiries:
 * the access JWT's own ``exp`` (so we know whether to use the token or
 * trigger refresh-and-back) AND the refresh window's ``exp`` (so we
 * know whether refresh-and-back will succeed or whether the user has
 * to log in again).
 */
interface AccessCookiePayload {
  access_token: string;
  access_exp: number; // epoch seconds
  refresh_exp: number; // epoch seconds — copied so SCs don't need ``rag_rt``
}

/** What we pack into the ``rag_rt`` cookie (visible only to ``/api/auth/*``). */
interface RefreshCookiePayload {
  refresh_token: string;
  exp: number;
}

// ---------------------------------------------------------------------------
// Encoding helpers
// ---------------------------------------------------------------------------

function encodeEnvelope<T>(payload: T): string {
  return Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
}

function decodeEnvelope<T>(
  raw: string | undefined,
  validate: (parsed: unknown) => parsed is T
): T | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(Buffer.from(raw, "base64url").toString("utf8"));
    return validate(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function isAccessPayload(value: unknown): value is AccessCookiePayload {
  return (
    !!value &&
    typeof value === "object" &&
    typeof (value as AccessCookiePayload).access_token === "string" &&
    typeof (value as AccessCookiePayload).access_exp === "number" &&
    typeof (value as AccessCookiePayload).refresh_exp === "number"
  );
}

function isRefreshPayload(value: unknown): value is RefreshCookiePayload {
  return (
    !!value &&
    typeof value === "object" &&
    typeof (value as RefreshCookiePayload).refresh_token === "string" &&
    typeof (value as RefreshCookiePayload).exp === "number"
  );
}

// ---------------------------------------------------------------------------
// READ-ONLY surface (safe in Server Components)
// ---------------------------------------------------------------------------

/**
 * Read the session cookies and return a ``Session`` snapshot.
 *
 * The access cookie carries everything a Server Component needs:
 *   - the access JWT itself
 *   - its own expiry
 *   - the refresh window's expiry (copied at write time)
 *
 * So this function returns a usable ``Session`` even when ``rag_rt``
 * is invisible (which is the case for any caller running outside of
 * ``/api/auth/*``). ``refresh_token`` will be ``null`` in that case;
 * route handlers under ``/api/auth/*`` get the real value.
 *
 * Falls back to the legacy single-cookie format so a rolling deploy
 * doesn't log out everyone the moment the new code lands. The legacy
 * cookie is wiped on the first ``setSession`` call.
 */
export async function getSession(): Promise<Session | null> {
  const store = await cookies();

  const accessPayload = decodeEnvelope(store.get(ACCESS_COOKIE)?.value, isAccessPayload);

  if (accessPayload) {
    const refreshPayload = decodeEnvelope(
      store.get(REFRESH_COOKIE)?.value,
      isRefreshPayload
    );
    return {
      access_token: accessPayload.access_token,
      refresh_token: refreshPayload?.refresh_token ?? null,
      access_expires_at: accessPayload.access_exp,
      refresh_expires_at: accessPayload.refresh_exp,
    };
  }

  // ---- legacy fallback (P-AUTH-1 single-cookie format) ----
  const legacyRaw = store.get(LEGACY_COMBINED_COOKIE_NAME)?.value;
  if (!legacyRaw) return null;
  try {
    const decoded = Buffer.from(legacyRaw, "base64url").toString("utf8");
    const parsed = JSON.parse(decoded) as {
      access_token?: string;
      refresh_token?: string;
      access_expires_at?: number;
      refresh_expires_at?: number;
    };
    if (
      !parsed.access_token ||
      !parsed.refresh_token ||
      typeof parsed.access_expires_at !== "number" ||
      typeof parsed.refresh_expires_at !== "number"
    ) {
      return null;
    }
    return {
      access_token: parsed.access_token,
      refresh_token: parsed.refresh_token,
      access_expires_at: parsed.access_expires_at,
      refresh_expires_at: parsed.refresh_expires_at,
    };
  } catch {
    return null;
  }
}

/**
 * Session state classification used by Server Components to decide
 * between "use the access token", "bounce through refresh-and-back",
 * and "clear cookie + go to /login".
 */
type SessionState =
  | { kind: "valid"; access_token: string }
  | { kind: "needs_refresh" } // access expired but refresh still valid
  | { kind: "anonymous" }; // no cookie / refresh expired / malformed

async function classifySession(): Promise<SessionState> {
  const s = await getSession();
  if (!s) return { kind: "anonymous" };
  const now = Math.floor(Date.now() / 1000);
  if (s.access_expires_at - now > CLOCK_SKEW_S) {
    return { kind: "valid", access_token: s.access_token };
  }
  if (s.refresh_expires_at - now > 0) {
    return { kind: "needs_refresh" };
  }
  return { kind: "anonymous" };
}

/**
 * Returns the access token if it's still valid (with a 30s clock-skew
 * buffer). Returns null when expired or missing — does NOT attempt
 * refresh because cookie writes are forbidden in Server Components.
 *
 * Most callers should prefer ``requireAccessToken`` which transparently
 * bounces through a Route Handler to perform the refresh. Use this raw
 * helper only when you need to make an optional decision based on the
 * presence of a token.
 */
export async function getAccessToken(): Promise<string | null> {
  const state = await classifySession();
  return state.kind === "valid" ? state.access_token : null;
}

export async function getCurrentUser(): Promise<UserOut | null> {
  const token = await getAccessToken();
  if (!token) return null;
  try {
    return await authApi.me(token);
  } catch {
    return null;
  }
}

/**
 * Best-effort recovery of the current request's path so callers don't
 * have to thread it through manually. Relies on the ``x-pathname``
 * header that the proxy middleware injects on every non-public route.
 */
export async function currentPathname(): Promise<string | undefined> {
  try {
    const h = await headers();
    const p = h.get("x-pathname") || undefined;
    return p && p.startsWith("/") ? p : undefined;
  } catch {
    return undefined;
  }
}

function buildRedirectTarget(
  base: "refresh" | "clear",
  next: string | undefined
): string {
  const path =
    base === "refresh" ? "/api/auth/refresh-and-back" : "/api/auth/clear-and-login";
  // Only forward same-origin app paths to avoid open-redirect AND to
  // prevent loops where the bridge route bounces back to itself.
  const safe =
    next &&
    next.startsWith("/") &&
    !next.startsWith("//") &&
    !next.startsWith("/api/auth")
      ? next
      : null;
  return safe ? `${path}?next=${encodeURIComponent(safe)}` : path;
}

/**
 * Server Component helper — returns a valid access token, or redirects
 * the request to a Route Handler that will produce one (or send the
 * user to /login if even the refresh has expired).
 *
 * Three branches:
 *   1. Access still valid               → return the token.
 *   2. Access expired, refresh valid    → 302 to /api/auth/refresh-and-back
 *      which rotates the cookies and 302s back to ``next`` (or ``/chat``).
 *   3. No session / refresh expired     → 302 to /api/auth/clear-and-login
 *      which wipes any stale cookies and redirects to /login.
 *
 * ``next`` should be the current pathname (+ search) so the user lands
 * back on the page they were trying to view.
 */
export async function requireAccessToken(next?: string): Promise<string> {
  const state = await classifySession();
  if (state.kind === "valid") return state.access_token;
  const resolvedNext = next ?? (await currentPathname());
  const target = buildRedirectTarget(
    state.kind === "needs_refresh" ? "refresh" : "clear",
    resolvedNext
  );
  redirect(target);
}

/**
 * Higher-level helper for pages that need the user object too. Returns
 * the validated access token + user; redirects on the same three
 * branches as ``requireAccessToken``. Treats a successful token + a
 * failed ``/me`` call (e.g. user deactivated mid-session) as a clean
 * logout so the user is never stuck on a half-rendered page.
 */
export async function requireUser(
  next?: string
): Promise<{ token: string; user: UserOut }> {
  const token = await requireAccessToken(next);
  try {
    const user = await authApi.me(token);
    return { token, user };
  } catch {
    const resolvedNext = next ?? (await currentPathname());
    redirect(buildRedirectTarget("clear", resolvedNext));
  }
}

// ---------------------------------------------------------------------------
// WRITE surface (Server Actions / Route Handlers only)
// ---------------------------------------------------------------------------

/**
 * Persist a fresh ``TokenPair`` into the access + refresh cookies.
 *
 * Always wipes the legacy single-cookie format so a session migrating
 * from P-AUTH-1 cookies converges in a single write rather than
 * lingering in a half-old state.
 */
export async function setSession(pair: TokenPair): Promise<void> {
  const store = await cookies();
  const accessExp = Math.floor(new Date(pair.access_expires_at).getTime() / 1000);
  const refreshExp = Math.floor(new Date(pair.refresh_expires_at).getTime() / 1000);
  const cookieMaxAge = Math.max(0, refreshExp - Math.floor(Date.now() / 1000));

  store.set({
    name: ACCESS_COOKIE,
    value: encodeEnvelope<AccessCookiePayload>({
      access_token: pair.access_token,
      access_exp: accessExp,
      // Copying the refresh window expiry here is the trick that lets
      // Server Components classify the session without seeing the
      // refresh cookie (which is scoped to ``/api/auth``).
      refresh_exp: refreshExp,
    }),
    httpOnly: true,
    secure: env.SESSION_COOKIE_SECURE,
    sameSite: "lax",
    path: "/",
    domain: env.SESSION_COOKIE_DOMAIN,
    // Tie the cookie's max-age to the refresh expiry so the access
    // cookie outlives the access JWT itself — that lets us detect
    // "expired access, recoverable" instead of the browser eating
    // the cookie behind our back.
    maxAge: cookieMaxAge,
  });

  store.set({
    name: REFRESH_COOKIE,
    value: encodeEnvelope<RefreshCookiePayload>({
      refresh_token: pair.refresh_token,
      exp: refreshExp,
    }),
    httpOnly: true,
    secure: env.SESSION_COOKIE_SECURE,
    // The refresh cookie should never travel on cross-site requests.
    sameSite: "strict",
    path: REFRESH_COOKIE_PATH,
    domain: env.SESSION_COOKIE_DOMAIN,
    maxAge: cookieMaxAge,
  });

  // Drop the legacy combined cookie if it's hanging around.
  if (LEGACY_COMBINED_COOKIE_NAME && store.get(LEGACY_COMBINED_COOKIE_NAME)) {
    store.set({
      name: LEGACY_COMBINED_COOKIE_NAME,
      value: "",
      path: "/",
      domain: env.SESSION_COOKIE_DOMAIN,
      maxAge: 0,
    });
  }
}

export async function clearSession(): Promise<void> {
  const store = await cookies();

  // Browsers honour cookie deletion only when ``Path`` and ``Domain``
  // match the original Set-Cookie, so clear each cookie at its own
  // path. We also wipe the legacy cookie name for users mid-rolling
  // deploy.
  store.set({
    name: ACCESS_COOKIE,
    value: "",
    path: "/",
    domain: env.SESSION_COOKIE_DOMAIN,
    maxAge: 0,
  });
  store.set({
    name: REFRESH_COOKIE,
    value: "",
    path: REFRESH_COOKIE_PATH,
    domain: env.SESSION_COOKIE_DOMAIN,
    maxAge: 0,
  });
  if (LEGACY_COMBINED_COOKIE_NAME) {
    store.set({
      name: LEGACY_COMBINED_COOKIE_NAME,
      value: "",
      path: "/",
      domain: env.SESSION_COOKIE_DOMAIN,
      maxAge: 0,
    });
  }
}

/**
 * Returns a valid access token, transparently refreshing if expired.
 * Writes the rotated pair back into the session cookies.
 *
 * Throws-safe: returns null on any failure (expired refresh, network
 * error, malformed cookie). Caller should treat null as "not signed in".
 *
 * MUST only be called from a Server Action or Route Handler — Server
 * Component renders cannot mutate cookies.
 */
export async function getAccessTokenWithRefresh(): Promise<string | null> {
  const s = await getSession();
  if (!s) return null;

  const now = Math.floor(Date.now() / 1000);
  if (s.access_expires_at - now > CLOCK_SKEW_S) return s.access_token;

  if (s.refresh_expires_at - now <= 0) {
    await clearSession();
    return null;
  }

  // ``rag_rt`` is scoped to ``/api/auth`` so only callers running under
  // that prefix (i.e. ``refresh-and-back`` and ``logout``) actually
  // receive the cookie. Other Route Handlers (``/api/chat/...`` etc.)
  // get ``null`` here — the access cookie alone tells them the session
  // is recoverable, but they cannot perform the rotation themselves.
  // Falling back to a redirect-style flow keeps every BFF endpoint
  // honest: when their access expires they bounce through
  // ``refresh-and-back`` rather than each minting their own pair.
  if (!s.refresh_token) {
    return null;
  }

  try {
    const pair = await authApi.refresh(s.refresh_token);
    await setSession(pair);
    return pair.access_token;
  } catch {
    await clearSession();
    return null;
  }
}
