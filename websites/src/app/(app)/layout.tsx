import { GlobalRail } from "@/components/shell/global-rail";
import { resolveActiveOrg } from "@/lib/org/active-org.server";
import { orgApi, providerApi } from "@/lib/api";
import { ApiError, type OrgOut } from "@/lib/api/shared/types";
import { requireUser } from "@/lib/auth/session.server";

export const dynamic = "force-dynamic";

/**
 * Thin app shell — just authenticates the request and renders the
 * global navigation rail. Per-module sidebars (chat sessions, wiki
 * page tree, …) live inside their own route-group layouts so they
 * don't bleed into unrelated pages.
 *
 * ``requireUser`` transparently bridges the "access expired but
 * refresh still valid" gap by 302-ing the request through a Route
 * Handler that rotates the cookie. Without it, a page reload after
 * the 15-minute access TTL would unconditionally land on /login.
 */
export default async function AppLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const { token, user } = await requireUser();

  // Eagerly trigger the provider-seed onboarding so the chat toolbar's
  // model selector picks up the starter Ollama provider on first
  // render. The /providers list is cheap on a hot DB connection.
  try {
    await providerApi.listProviders(token);
  } catch (err) {
    if (!(err instanceof ApiError)) throw err;
    console.warn("provider bootstrap skipped:", err.message);
  }

  let orgs: OrgOut[] = [];
  try {
    orgs = await orgApi.listOrgs(token);
  } catch (err) {
    if (err instanceof ApiError) {
      console.warn("listOrgs failed:", err.message);
    } else {
      throw err;
    }
  }
  const activeOrg = await resolveActiveOrg(orgs);

  return (
    <div className="flex h-dvh w-full overflow-hidden md:h-screen">
      <GlobalRail user={user} orgs={orgs} activeOrgId={activeOrg?.id ?? null} />
      <main className="min-w-0 flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
