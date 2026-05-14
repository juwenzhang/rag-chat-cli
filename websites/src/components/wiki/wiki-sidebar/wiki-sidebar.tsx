"use client";

import {
  Book,
  ChevronsLeft,
  ChevronsRight,
  ChevronsUpDown,
  Lock,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { api } from "@/lib/api/browser";
import type { OrgOut, WikiOut, WikiPageListOut } from "@/lib/api/types";

import { CreateWikiDialog } from "./create-wiki-dialog";
import { PageRow } from "./page-row";
import { TreeBranch } from "./tree-branch";
import { buildTree } from "./tree";

interface Props {
  activeOrg: OrgOut;
  wikis: WikiOut[];
  activeWiki: WikiOut | null;
  pages: WikiPageListOut[];
}

/** Two-level wiki sidebar — workspace/wiki switcher above the page tree. */
export function WikiSidebar({ activeOrg, wikis, activeWiki, pages }: Props) {
  const router = useRouter();
  const params = useParams();
  const activePageId =
    typeof params.pageId === "string" ? params.pageId : null;
  const urlWikiId =
    typeof params.wikiId === "string" ? params.wikiId : null;

  // This sidebar lives in `wiki/layout.tsx`, which the App Router keeps
  // mounted across navigations within `/wiki/*` — so `activeWiki` /
  // `pages` go stale the moment you switch wikis client-side. When the
  // URL's wiki diverges from the layout-provided prop, force a refresh
  // so the layout re-runs and hands down the correct tree. Guarded on
  // `wikis` membership so an unresolvable id can't spin a refresh loop.
  useEffect(() => {
    if (!urlWikiId || urlWikiId === activeWiki?.id) return;
    if (!wikis.some((w) => w.id === urlWikiId)) return;
    router.refresh();
  }, [urlWikiId, activeWiki?.id, wikis, router]);

  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [pendingDelete, setPendingDelete] =
    useState<WikiPageListOut | null>(null);
  const [pendingWikiDelete, setPendingWikiDelete] =
    useState<WikiOut | null>(null);
  const [createWikiOpen, setCreateWikiOpen] = useState(false);

  // Optimistic title overrides, keyed by page id. The wiki editor lives
  // in a sibling subtree with no shared state, so it broadcasts title
  // edits on a `window` event; we fold them in here for instant feedback
  // (the server-fetched `pages` prop catches up on the next layout run).
  const [titleOverrides, setTitleOverrides] = useState<
    Record<string, string>
  >({});
  useEffect(() => {
    const onTitle = (e: Event) => {
      const detail = (e as CustomEvent<{ pageId: string; title: string }>)
        .detail;
      if (!detail?.pageId) return;
      setTitleOverrides((prev) => ({ ...prev, [detail.pageId]: detail.title }));
    };
    window.addEventListener("wiki:page-title", onTitle);
    return () => window.removeEventListener("wiki:page-title", onTitle);
  }, []);

  const canEditWiki = activeWiki && activeWiki.role !== "viewer";
  const orgCanCreateWiki = activeOrg.role !== "viewer";

  // Fold optimistic title overrides onto the server-fetched pages once,
  // up front — `buildTree` and search then render the live titles for
  // free, no prop-threading down to `PageRow`.
  const effectivePages = useMemo(
    () =>
      pages.map((p) =>
        titleOverrides[p.id] != null
          ? { ...p, title: titleOverrides[p.id] }
          : p
      ),
    [pages, titleOverrides]
  );

  const tree = useMemo(() => buildTree(effectivePages), [effectivePages]);
  const searchHits = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    return effectivePages.filter((p) => p.title.toLowerCase().includes(q));
  }, [effectivePages, query]);

  const createPage = async (parentId?: string) => {
    if (!activeWiki || creating) return;
    setCreating(true);
    try {
      const page = await api.wikis.createPage(
        activeWiki.id,
        parentId ? { parent_id: parentId } : {}
      );
      router.push(`/wiki/${activeWiki.id}/p/${page.id}`);
      router.refresh();
    } catch {
      toast.error("Failed to create page");
    } finally {
      setCreating(false);
    }
  };

  const onDeletePage = async () => {
    if (!pendingDelete) return;
    try {
      await api.wikiPages.remove(pendingDelete.id);
    } catch (err) {
      toast.error("Failed to delete page");
      throw err;
    }
    toast.success("Page deleted");
    if (activePageId === pendingDelete.id && activeWiki) {
      router.push(`/wiki/${activeWiki.id}`);
    }
    router.refresh();
  };

  const onDeleteWiki = async () => {
    if (!pendingWikiDelete) return;
    try {
      await api.wikis.remove(pendingWikiDelete.id);
    } catch (err) {
      toast.error((err as Error).message || "Failed to delete wiki");
      throw err;
    }
    toast.success("Wiki deleted");
    router.push("/wiki");
    router.refresh();
  };

  if (collapsed) {
    return (
      <aside className="flex h-full w-12 shrink-0 flex-col items-center border-r border-border bg-card/40 py-2">
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setCollapsed(false)}
                aria-label="Expand sidebar"
              >
                <ChevronsRight />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">Expand</TooltipContent>
          </Tooltip>
          {canEditWiki && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => void createPage()}
                  disabled={creating}
                  aria-label="New page"
                  className="mt-1"
                >
                  <Plus />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">New page</TooltipContent>
            </Tooltip>
          )}
        </TooltipProvider>
      </aside>
    );
  }

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-border bg-card/40">
      {/* Workspace + wiki switcher header */}
      <div className="border-b border-border px-3 py-3">
        <p className="truncate text-[10px] uppercase tracking-wider text-muted-foreground">
          {activeOrg.name}
        </p>
        <div className="mt-1 flex items-center gap-1">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="flex min-w-0 flex-1 items-center gap-1.5 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-accent"
              >
                <Book className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate text-sm font-semibold">
                  {activeWiki ? activeWiki.name : "All wikis"}
                </span>
                {activeWiki?.visibility === "private" && (
                  <Lock className="size-3 shrink-0 text-muted-foreground" />
                )}
                <ChevronsUpDown className="size-3 shrink-0 text-muted-foreground" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-60">
              <DropdownMenuLabel>Wikis in {activeOrg.name}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {wikis.length === 0 && (
                <p className="px-2 py-2 text-xs text-muted-foreground">
                  No wikis yet.
                </p>
              )}
              {wikis.map((w) => (
                <DropdownMenuItem key={w.id} asChild>
                  <Link
                    href={`/wiki/${w.id}`}
                    className="flex items-center gap-2"
                  >
                    <Book className="size-3.5 text-muted-foreground" />
                    <span className="flex-1 truncate">{w.name}</span>
                    {w.visibility === "private" && (
                      <Lock className="size-3 text-muted-foreground" />
                    )}
                  </Link>
                </DropdownMenuItem>
              ))}
              {orgCanCreateWiki && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onSelect={(e) => {
                      e.preventDefault();
                      setCreateWikiOpen(true);
                    }}
                  >
                    <Plus />
                    New wiki…
                  </DropdownMenuItem>
                </>
              )}
              {activeWiki && activeOrg.role === "owner" && (
                <DropdownMenuItem
                  onSelect={(e) => {
                    e.preventDefault();
                    setPendingWikiDelete(activeWiki);
                  }}
                  className="text-destructive focus:bg-destructive/10 focus:text-destructive"
                >
                  <Trash2 />
                  Delete this wiki
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setCollapsed(true)}
            aria-label="Collapse sidebar"
          >
            <ChevronsLeft />
          </Button>
        </div>
      </div>

      {/* Page tree (only when a wiki is selected) */}
      {activeWiki ? (
        <>
          {canEditWiki && (
            <div className="px-3 pt-3">
              <Button
                onClick={() => void createPage()}
                disabled={creating}
                className="w-full justify-start gap-2"
                size="sm"
              >
                <Plus className="size-3.5" />
                {creating ? "Creating…" : "New page"}
              </Button>
            </div>
          )}
          <div className="px-3 pt-3 pb-1">
            <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Pages
            </p>
          </div>
          <div className="relative px-3 pb-2">
            <Search className="pointer-events-none absolute left-6 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search pages…"
              className="h-8 pl-8 text-sm"
            />
          </div>

          <ScrollArea className="flex-1 px-1 pb-2">
            {pages.length === 0 ? (
              <p className="px-3 py-8 text-center text-xs text-muted-foreground">
                No pages yet.
              </p>
            ) : searchHits !== null ? (
              searchHits.length === 0 ? (
                <p className="px-3 py-6 text-center text-xs text-muted-foreground">
                  No matches.
                </p>
              ) : (
                <ul className="flex flex-col gap-0.5">
                  {searchHits.map((p) => (
                    <li key={p.id}>
                      <PageRow
                        wikiId={activeWiki.id}
                        page={p}
                        depth={0}
                        active={p.id === activePageId}
                        canEdit={!!canEditWiki}
                        onAddChild={() => void createPage(p.id)}
                        onRequestDelete={() => setPendingDelete(p)}
                      />
                    </li>
                  ))}
                </ul>
              )
            ) : (
              <ul className="flex flex-col gap-0.5">
                {tree.map((node) => (
                  <TreeBranch
                    key={node.page.id}
                    wikiId={activeWiki.id}
                    node={node}
                    depth={0}
                    activePageId={activePageId}
                    canEdit={!!canEditWiki}
                    onAddChild={(parentId) => void createPage(parentId)}
                    onRequestDelete={(p) => setPendingDelete(p)}
                  />
                ))}
              </ul>
            )}
          </ScrollArea>
        </>
      ) : (
        <div className="flex-1 px-3 py-4">
          <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Wikis
          </p>
          {wikis.length === 0 ? (
            <p className="py-6 text-xs text-muted-foreground">
              No wikis yet.
            </p>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {wikis.map((w) => (
                <li key={w.id}>
                  <Link
                    href={`/wiki/${w.id}`}
                    className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent"
                  >
                    <Book className="size-3.5 text-muted-foreground" />
                    <span className="flex-1 truncate">{w.name}</span>
                    {w.visibility === "private" && (
                      <Lock className="size-3 text-muted-foreground" />
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Delete this page?"
        description={
          <>
            <span className="font-medium text-foreground">
              {pendingDelete?.title || "Untitled"}
            </span>{" "}
            will be removed. Child pages lose their parent and move to the
            root.
          </>
        }
        confirmLabel="Delete"
        destructive
        onConfirm={onDeletePage}
      />

      <ConfirmDialog
        open={pendingWikiDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingWikiDelete(null);
        }}
        title={`Delete ${pendingWikiDelete?.name ?? "this wiki"}?`}
        description="All pages in this wiki will be removed. This can't be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={onDeleteWiki}
      />

      <CreateWikiDialog
        open={createWikiOpen}
        onOpenChange={setCreateWikiOpen}
        orgId={activeOrg.id}
        onCreated={(w) => {
          router.push(`/wiki/${w.id}`);
          router.refresh();
        }}
      />
    </aside>
  );
}
