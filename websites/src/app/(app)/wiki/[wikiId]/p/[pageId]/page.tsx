import { redirect } from "next/navigation";

import { WikiEditorClient } from "@/components/wiki/wiki-editor-client";
import { orgApi, wikiApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { getAccessToken, getCurrentUser } from "@/lib/session";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ wikiId: string; pageId: string }>;
}

export default async function WikiPagePage({ params }: Props) {
  const { wikiId, pageId } = await params;
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  const token = await getAccessToken();
  if (!token) redirect("/login");

  let page;
  try {
    page = await wikiApi.getPage(token, pageId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      redirect(`/wiki/${wikiId}`);
    }
    throw err;
  }

  // Belt-and-braces: if the URL's wikiId doesn't match the page's
  // actual wiki (e.g. the page was moved), redirect to the right path
  // so the breadcrumb and sidebar are coherent.
  if (page.wiki_id !== wikiId) {
    redirect(`/wiki/${page.wiki_id}/p/${page.id}`);
  }

  const wiki = await wikiApi.getWiki(token, wikiId);
  const orgs = await orgApi.listOrgs(token);
  const allWikis = await wikiApi.listWikis(token, wiki.org_id);

  return (
    // ``key`` forces a fresh component instance when the user
    // navigates between pages so the textarea's local state resets
    // cleanly without a stale-content flash.
    <WikiEditorClient
      key={page.id}
      page={page}
      wiki={wiki}
      role={wiki.role}
      orgs={orgs}
      writableWikis={allWikis.filter((w) => w.role !== "viewer")}
    />
  );
}
