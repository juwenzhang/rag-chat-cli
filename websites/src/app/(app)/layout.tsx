import { redirect } from "next/navigation";

import { GlobalRail } from "@/components/shell/global-rail";
import { resolveActiveOrg } from "@/lib/active-org";
import { orgApi, providerApi } from "@/lib/api";
import { ApiError, type OrgOut } from "@/lib/api/types";
import { getAccessToken, getCurrentUser } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Thin app shell — just authenticates the request and renders the
 * global navigation rail. Per-module sidebars (chat sessions, wiki
 * page tree, …) live inside their own route-group layouts so they
 * don't bleed into unrelated pages.
 */
export default async function AppLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const user = await getCurrentUser();
  if (!user) redirect("/api/auth/clear-and-login");

  const token = await getAccessToken();
  if (!token) redirect("/api/auth/clear-and-login");

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
    <div className="flex h-screen w-full overflow-hidden">
      <GlobalRail user={user} orgs={orgs} activeOrgId={activeOrg?.id ?? null} />
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
