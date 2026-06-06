import { redirect } from "next/navigation";

import { WikiSettingsClient } from "@/features/wiki/components/wiki-settings-client";
import { wikiApi } from "@/lib/api";
import { ApiError } from "@/lib/api/shared/types";
import { requireUser } from "@/lib/auth/session.server";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ wikiId: string }>;
}

export default async function WikiSettingsPage({ params }: Props) {
  const { wikiId } = await params;
  const { token, user } = await requireUser();

  let wiki;
  try {
    wiki = await wikiApi.getWiki(token, wikiId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) redirect("/wiki");
    throw err;
  }
  // For private wikis we also fetch the explicit member list. For
  // org_wide wikis the members panel is hidden (access is inherited),
  // so the fetch would just waste a round-trip.
  const members =
    wiki.visibility === "private" ? await wikiApi.listWikiMembers(token, wikiId) : [];
  return <WikiSettingsClient currentUserId={user.id} wiki={wiki} members={members} />;
}
