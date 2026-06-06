import { redirect } from "next/navigation";

import { resolveActiveOrg } from "@/lib/org/active-org.server";
import { orgApi } from "@/lib/api";
import { requireAccessToken } from "@/lib/auth/session.server";

import { NewWikiClient } from "@/features/wiki/components/new-wiki-client";

export const dynamic = "force-dynamic";

export default async function NewWikiPage() {
  const token = await requireAccessToken();
  const orgs = await orgApi.listOrgs(token);
  const activeOrg = await resolveActiveOrg(orgs);
  if (!activeOrg) redirect("/orgs");
  if (activeOrg.role === "viewer") redirect("/wiki");
  return <NewWikiClient orgId={activeOrg.id} orgName={activeOrg.name} />;
}
