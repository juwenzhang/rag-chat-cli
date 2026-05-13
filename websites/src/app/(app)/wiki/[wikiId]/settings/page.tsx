import { redirect } from "next/navigation";

import { wikiApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { getAccessToken, getCurrentUser } from "@/lib/session";

import { WikiSettingsClient } from "./wiki-settings-client";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ wikiId: string }>;
}

export default async function WikiSettingsPage({ params }: Props) {
  const { wikiId } = await params;
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  const token = await getAccessToken();
  if (!token) redirect("/login");

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
    wiki.visibility === "private"
      ? await wikiApi.listWikiMembers(token, wikiId)
      : [];
  return (
    <WikiSettingsClient
      currentUserId={user.id}
      wiki={wiki}
      members={members}
    />
  );
}
