import { redirect } from "next/navigation";

import { orgApi } from "@/lib/api";
import { getAccessToken, getCurrentUser } from "@/lib/session";

import { OrgsPageClient } from "./orgs-page-client";

export const dynamic = "force-dynamic";

export default async function OrgsPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  const token = await getAccessToken();
  if (!token) redirect("/login");
  const orgs = await orgApi.listOrgs(token);
  return <OrgsPageClient currentUserId={user.id} orgs={orgs} />;
}
