import { OrgsPageClient } from "@/features/orgs/components/orgs-page-client";
import { orgApi } from "@/lib/api";
import { requireUser } from "@/lib/auth/session.server";

export const dynamic = "force-dynamic";

export default async function OrgsPage() {
  const { token, user } = await requireUser();
  const orgs = await orgApi.listOrgs(token);
  return <OrgsPageClient currentUserId={user.id} orgs={orgs} />;
}
