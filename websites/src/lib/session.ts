/**
 * Server-side session management — cookie-backed.
 *
 * The session cookie stores a base64-encoded JSON `TokenPair` (access +
 * refresh). It's HttpOnly, Secure (in prod), SameSite=Lax. The browser
 * never sees the access token in JS — only the BFF route handlers do.
 *
 * Two surfaces, distinguished by write capability:
 *
 *   - `getSession()`, `getCurrentUser()`, `getAccessToken()` are READ-ONLY
 *     and safe to call from any context, including Server Components.
 *     They will *not* refresh an expired access token because cookies
 *     can only be mutated from Server Actions / Route Handlers.
 *
 *   - `getAccessTokenWithRefresh()`, `setSession()`, `clearSession()`
 *     all WRITE the cookie. They must be called from a Server Action
 *     or Route Handler. The Server Component code path simply redirects
 *     to /login if the read-only token check fails.
 */

import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { env } from "@/lib/env";
import { authApi } from "@/lib/api";
import type { TokenPair, UserOut } from "@/lib/api/types";

const REFRESH_TTL_S = 60 * 60 * 24 * 7; // 7 days — cookie lifetime ceiling
const CLOCK_SKEW_S = 30;

export interface Session {
  access_token: string;
  refresh_token: string;
  access_expires_at: number; // epoch seconds
  refresh_expires_at: number;
}

function pairToSession(pair: TokenPair): Session {
  return {
    access_token: pair.access_token,
    refresh_token: pair.refresh_token,
    access_expires_at: Math.floor(new Date(pair.access_expires_at).getTime() / 1000),
    refresh_expires_at: Math.floor(new Date(pair.refresh_expires_at).getTime() / 1000),
  };
}

// ---------------------------------------------------------------------------
// READ-ONLY surface (safe in Server Components)
// ---------------------------------------------------------------------------

export async function getSession(): Promise<Session | null> {
  const store = await cookies();
  const raw = store.get(env.SESSION_COOKIE_NAME)?.value;
  if (!raw) return null;
  try {
    const decoded = Buffer.from(raw, "base64url").toString("utf8");
    const parsed = JSON.parse(decoded) as Session;
    if (!parsed.access_token || !parsed.refresh_token) return null;
    return parsed;
  } catch {
    return null;
  }
}

/**
 * Returns the access token if it's still valid (with a 30s clock-skew
 * buffer). Returns null when expired — does NOT attempt refresh because
 * cookie writes are forbidden in Server Components.
 *
 * Use this from Server Components. Use `getAccessTokenWithRefresh` from
 * Route Handlers / Server Actions.
 */
export async function getAccessToken(): Promise<string | null> {
  const s = await getSession();
  if (!s) return null;
  const now = Math.floor(Date.now() / 1000);
  return s.access_expires_at - now > CLOCK_SKEW_S ? s.access_token : null;
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
 * Server Component helper — returns a valid access token or redirects to
 * the clear-and-login route (which wipes the stale cookie before sending
 * the user to /login). Use this instead of throwing so the user lands
 * on a sensible page rather than seeing an error frame.
 */
export async function requireAccessToken(next?: string): Promise<string> {
  const t = await getAccessToken();
  if (t) return t;
  const target = next
    ? `/api/auth/clear-and-login?next=${encodeURIComponent(next)}`
    : "/api/auth/clear-and-login";
  redirect(target);
}

// ---------------------------------------------------------------------------
// WRITE surface (Server Actions / Route Handlers only)
// ---------------------------------------------------------------------------

export async function setSession(pair: TokenPair): Promise<void> {
  const store = await cookies();
  const session = pairToSession(pair);
  const value = Buffer.from(JSON.stringify(session), "utf8").toString("base64url");

  store.set({
    name: env.SESSION_COOKIE_NAME,
    value,
    httpOnly: true,
    secure: env.SESSION_COOKIE_SECURE,
    sameSite: "lax",
    path: "/",
    domain: env.SESSION_COOKIE_DOMAIN,
    maxAge: REFRESH_TTL_S,
  });
}

export async function clearSession(): Promise<void> {
  const store = await cookies();
  store.set({
    name: env.SESSION_COOKIE_NAME,
    value: "",
    httpOnly: true,
    secure: env.SESSION_COOKIE_SECURE,
    sameSite: "lax",
    path: "/",
    domain: env.SESSION_COOKIE_DOMAIN,
    maxAge: 0,
  });
}

/**
 * Returns a valid access token, transparently refreshing if expired.
 * Writes the rotated pair back into the session cookie.
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

  try {
    const pair = await authApi.refresh(s.refresh_token);
    await setSession(pair);
    return pair.access_token;
  } catch {
    await clearSession();
    return null;
  }
}
