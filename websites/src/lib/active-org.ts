import "server-only";

import { cookies } from "next/headers";

import type { OrgOut } from "@/lib/api/types";

const COOKIE_NAME = "active_org_id";
const ONE_YEAR_S = 60 * 60 * 24 * 365;

/**
 * Resolve the caller's "currently selected" org. Order of preference:
 *
 * 1. The id stored in the ``active_org_id`` cookie — *if it still
 *    points at an org the user is a member of*. We re-validate against
 *    the fetched list so a stale cookie from another account or a
 *    revoked membership never wins.
 * 2. The user's personal org (always present — see the migration /
 *    AuthService.register bootstrap).
 * 3. The first org in the list (defensive — shouldn't happen since
 *    every user has a personal org).
 */
export async function resolveActiveOrg(orgs: OrgOut[]): Promise<OrgOut | null> {
  if (orgs.length === 0) return null;
  const store = await cookies();
  const cookieId = store.get(COOKIE_NAME)?.value;
  const fromCookie = cookieId ? orgs.find((o) => o.id === cookieId) : undefined;
  if (fromCookie) return fromCookie;
  const personal = orgs.find((o) => o.is_personal);
  return personal ?? orgs[0];
}

/**
 * Persist the user's active-org choice. Only callable from a Server
 * Action / Route Handler (Next forbids cookie writes in pages /
 * layouts).
 */
export async function setActiveOrg(orgId: string): Promise<void> {
  const store = await cookies();
  store.set({
    name: COOKIE_NAME,
    value: orgId,
    path: "/",
    maxAge: ONE_YEAR_S,
    sameSite: "lax",
    httpOnly: false, // read-only on the client is fine; nothing sensitive in it
  });
}
