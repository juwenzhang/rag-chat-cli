import { redirect } from "next/navigation";

import { getSession } from "@/lib/auth/session.server";

/**
 * Root entry point. We don't gate the route via ``requireAccessToken``
 * because the desired behaviour for anonymous users is "send them to
 * /login", not "bounce through the refresh bridge". So we look at the
 * raw cookie state directly:
 *
 *   - cookie present + refresh still valid → /chat (the refresh
 *     bridge inside /chat's layout will mint a new access if needed).
 *   - cookie present but refresh dead       → clear-and-login.
 *   - no cookie                              → /login.
 */
export default async function Home() {
  const session = await getSession();
  if (!session) redirect("/login");

  const now = Math.floor(Date.now() / 1000);
  if (session.refresh_expires_at - now > 0) {
    redirect("/chat");
  }
  redirect("/api/auth/clear-and-login");
}
