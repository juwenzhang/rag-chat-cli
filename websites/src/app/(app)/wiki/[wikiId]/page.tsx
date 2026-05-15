import { ArrowLeft, Book, FileText, Lock, Settings } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Button } from "@/components/ui/button";
import { wikiApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { getAccessToken, getCurrentUser } from "@/lib/session";

import { NewPageButton } from "./new-page-button";
import { PageTableClient } from "./page-table-client";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ wikiId: string }>;
}

/**
 * /wiki/{wikiId} — wiki overview + page list.
 *
 * Feishu-style: title + description header, then a flat row-per-page
 * list (not cards). Click a row → /wiki/{wikiId}/p/{pageId}.
 */
export default async function WikiHomePage({ params }: Props) {
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
  const pages = await wikiApi.listPages(token, wikiId);
  const canEdit = wiki.role !== "viewer";

  return (
    <div className="mx-auto w-full max-w-4xl px-4 pb-16 pt-6 sm:px-8 sm:pt-10">
      <Button asChild variant="ghost" size="sm" className="mb-4 -ml-2">
        <Link href="/wiki">
          <ArrowLeft />
          All wikis
        </Link>
      </Button>

      <header className="mb-8 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1.5">
          <div className="flex items-center gap-2">
            <div className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Book className="size-4" />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight">
              {wiki.name}
            </h1>
            {wiki.visibility === "private" && (
              <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                <Lock className="size-3" />
                Private
              </span>
            )}
          </div>
          {wiki.description && (
            <p className="text-sm text-muted-foreground">{wiki.description}</p>
          )}
          <p className="text-xs text-muted-foreground">
            {pages.length} page{pages.length === 1 ? "" : "s"} ·{" "}
            <span className="capitalize">{wiki.role}</span> access
          </p>
        </div>
        <div className="flex items-center gap-2">
          {canEdit && <NewPageButton wikiId={wiki.id} />}
          <Button asChild variant="outline" size="sm">
            <Link href={`/wiki/${wiki.id}/settings`}>
              <Settings />
              Settings
            </Link>
          </Button>
        </div>
      </header>

      {pages.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-card/40 p-10 text-center">
          <FileText className="mx-auto size-8 text-muted-foreground/50" />
          <p className="mt-3 text-sm font-medium">No pages yet</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {canEdit
              ? "Click New page above or use the + in the sidebar."
              : "Pages will appear here once an editor adds them."}
          </p>
        </div>
      ) : (
        <PageTableClient wikiId={wiki.id} pages={pages} canEdit={canEdit} />
      )}
    </div>
  );
}
