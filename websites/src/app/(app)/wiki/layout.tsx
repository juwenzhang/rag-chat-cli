import { redirect } from "next/navigation";

import { WikiSidebar } from "@/components/wiki/wiki-sidebar";
import { resolveActiveOrg } from "@/lib/active-org";
import { orgApi, wikiApi } from "@/lib/api";
import {
  ApiError,
  type WikiOut,
  type WikiPageListOut,
} from "@/lib/api/types";
import { getAccessToken, getCurrentUser } from "@/lib/session";
import { headers } from "next/headers";

export const dynamic = "force-dynamic";

/**
 * Wiki sub-shell — renders the two-level sidebar (workspace's wikis
 * across the top, current wiki's page tree below) next to the global
 * rail.
 *
 * The "active wiki" is derived from the URL: any path under
 * ``/wiki/{wiki_id}/...`` selects that wiki; ``/wiki`` itself is the
 * picker view (no specific wiki selected).
 */
export default async function WikiLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  const token = await getAccessToken();
  if (!token) redirect("/login");

  const orgs = await orgApi.listOrgs(token);
  const activeOrg = await resolveActiveOrg(orgs);
  if (!activeOrg) redirect("/orgs");

  let wikis: WikiOut[] = [];
  try {
    wikis = await wikiApi.listWikis(token, activeOrg.id);
  } catch (err) {
    if (err instanceof ApiError) {
      console.warn("listWikis failed:", err.message);
    } else {
      throw err;
    }
  }

  // Pull the active wiki id out of the URL via x-pathname (set by the
  // Next middleware on every request). We avoid useParams here so this
  // stays a server component — useful so the page tree pre-renders.
  const hdrs = await headers();
  const pathname = hdrs.get("x-pathname") || hdrs.get("next-url") || "";
  const m = pathname.match(/^\/wiki\/([0-9a-f-]{36})/i);
  const activeWikiId = m ? m[1] : null;
  const activeWiki = activeWikiId
    ? wikis.find((w) => w.id === activeWikiId) ?? null
    : null;

  let pages: WikiPageListOut[] = [];
  if (activeWiki) {
    try {
      pages = await wikiApi.listPages(token, activeWiki.id);
    } catch (err) {
      if (err instanceof ApiError) {
        console.warn("listPages failed:", err.message);
      } else {
        throw err;
      }
    }
  }

  return (
    <div className="flex h-full">
      <WikiSidebar
        activeOrg={activeOrg}
        wikis={wikis}
        activeWiki={activeWiki}
        pages={pages}
      />
      <div className="flex-1 overflow-hidden">{children}</div>
    </div>
  );
}
