"use client";

import {
  Book,
  ChevronDown,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ChevronsUpDown,
  FileText,
  Lock,
  MoreHorizontal,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type {
  OrgOut,
  WikiOut,
  WikiPageListOut,
  WikiVisibility,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface Props {
  activeOrg: OrgOut;
  wikis: WikiOut[];
  activeWiki: WikiOut | null;
  pages: WikiPageListOut[];
}

interface TreeNode {
  page: WikiPageListOut;
  children: TreeNode[];
}

function buildTree(pages: WikiPageListOut[]): TreeNode[] {
  const byId = new Map<string, TreeNode>();
  for (const p of pages) byId.set(p.id, { page: p, children: [] });
  const roots: TreeNode[] = [];
  for (const node of byId.values()) {
    const parentId = node.page.parent_id;
    if (parentId && byId.has(parentId)) {
      byId.get(parentId)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  const sort = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.page.position !== b.page.position) {
        return a.page.position - b.page.position;
      }
      return b.page.updated_at.localeCompare(a.page.updated_at);
    });
    for (const n of nodes) sort(n.children);
  };
  sort(roots);
  return roots;
}

export function WikiSidebar({ activeOrg, wikis, activeWiki, pages }: Props) {
  const router = useRouter();
  const params = useParams();
  const activePageId =
    typeof params.pageId === "string" ? params.pageId : null;

  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [pendingDelete, setPendingDelete] =
    useState<WikiPageListOut | null>(null);
  const [pendingWikiDelete, setPendingWikiDelete] =
    useState<WikiOut | null>(null);
  const [createWikiOpen, setCreateWikiOpen] = useState(false);

  const canEditWiki = activeWiki && activeWiki.role !== "viewer";
  const orgCanCreateWiki = activeOrg.role !== "viewer";

  const tree = useMemo(() => buildTree(pages), [pages]);
  const searchHits = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return null;
    return pages.filter((p) => p.title.toLowerCase().includes(q));
  }, [pages, query]);

  const createPage = async (parentId?: string) => {
    if (!activeWiki || creating) return;
    setCreating(true);
    try {
      const res = await fetch(`/api/wikis/${activeWiki.id}/pages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parentId ? { parent_id: parentId } : {}),
      });
      if (!res.ok) {
        toast.error("Failed to create page");
        return;
      }
      const page = (await res.json()) as WikiPageListOut;
      router.push(`/wiki/${activeWiki.id}/p/${page.id}`);
      router.refresh();
    } finally {
      setCreating(false);
    }
  };

  const onDeletePage = async () => {
    if (!pendingDelete) return;
    const res = await fetch(`/api/wiki-pages/${pendingDelete.id}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      toast.error("Failed to delete page");
      throw new Error("delete failed");
    }
    toast.success("Page deleted");
    if (activePageId === pendingDelete.id && activeWiki) {
      router.push(`/wiki/${activeWiki.id}`);
    }
    router.refresh();
  };

  const onDeleteWiki = async () => {
    if (!pendingWikiDelete) return;
    const res = await fetch(`/api/wikis/${pendingWikiDelete.id}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { message?: string };
      toast.error(body.message || "Failed to delete wiki");
      throw new Error("delete failed");
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

function TreeBranch({
  wikiId,
  node,
  depth,
  activePageId,
  canEdit,
  onAddChild,
  onRequestDelete,
}: {
  wikiId: string;
  node: TreeNode;
  depth: number;
  activePageId: string | null;
  canEdit: boolean;
  onAddChild: (parentId: string) => void;
  onRequestDelete: (page: WikiPageListOut) => void;
}) {
  const [open, setOpen] = useState(true);
  const hasChildren = node.children.length > 0;
  return (
    <li>
      <PageRow
        wikiId={wikiId}
        page={node.page}
        depth={depth}
        active={node.page.id === activePageId}
        canEdit={canEdit}
        expanded={hasChildren ? open : undefined}
        onToggleExpand={hasChildren ? () => setOpen((v) => !v) : undefined}
        onAddChild={() => onAddChild(node.page.id)}
        onRequestDelete={() => onRequestDelete(node.page)}
      />
      {hasChildren && open && (
        <ul className="flex flex-col gap-0.5">
          {node.children.map((c) => (
            <TreeBranch
              key={c.page.id}
              wikiId={wikiId}
              node={c}
              depth={depth + 1}
              activePageId={activePageId}
              canEdit={canEdit}
              onAddChild={onAddChild}
              onRequestDelete={onRequestDelete}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function PageRow({
  wikiId,
  page,
  depth,
  active,
  canEdit,
  expanded,
  onToggleExpand,
  onAddChild,
  onRequestDelete,
}: {
  wikiId: string;
  page: WikiPageListOut;
  depth: number;
  active: boolean;
  canEdit: boolean;
  expanded?: boolean;
  onToggleExpand?: () => void;
  onAddChild: () => void;
  onRequestDelete: () => void;
}) {
  return (
    <div
      className={cn(
        "group relative flex items-center rounded-md transition-colors",
        "hover:bg-accent/60",
        active && "bg-accent text-accent-foreground"
      )}
      style={{ paddingLeft: 8 + depth * 14 }}
    >
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onToggleExpand?.();
        }}
        disabled={onToggleExpand === undefined}
        className={cn(
          "flex size-4 items-center justify-center rounded text-muted-foreground transition-colors",
          onToggleExpand && "hover:bg-muted hover:text-foreground"
        )}
        aria-label={expanded ? "Collapse" : "Expand"}
      >
        {expanded === undefined ? null : expanded ? (
          <ChevronDown className="size-3" />
        ) : (
          <ChevronRight className="size-3" />
        )}
      </button>

      <Link
        href={`/wiki/${wikiId}/p/${page.id}`}
        className="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 pl-1 pr-1 text-sm"
      >
        <FileText className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="truncate">{page.title || "Untitled"}</span>
      </Link>

      {canEdit && (
        <div className="flex items-center pr-1 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onAddChild();
            }}
            aria-label="Add child page"
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Plus className="size-3" />
          </button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                }}
                aria-label="Page menu"
                className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <MoreHorizontal className="size-3" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuItem
                onSelect={() => onRequestDelete()}
                className="text-destructive focus:bg-destructive/10 focus:text-destructive"
              >
                <Trash2 />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}
    </div>
  );
}

function CreateWikiDialog({
  open,
  onOpenChange,
  orgId,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  orgId: string;
  onCreated: (w: WikiOut) => void;
}) {
  const [name, setName] = useState("");
  const [visibility, setVisibility] = useState<WikiVisibility>("org_wide");
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      const res = await fetch(`/api/orgs/${orgId}/wikis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), visibility }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as {
          message?: string;
        };
        toast.error(body.message || "Failed to create wiki");
        return;
      }
      const wiki = (await res.json()) as WikiOut;
      toast.success("Wiki created");
      setName("");
      setVisibility("org_wide");
      onOpenChange(false);
      onCreated(wiki);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>New wiki</DialogTitle>
            <DialogDescription>
              A wiki is a named knowledge base inside this workspace. Its
              pages can be shared org-wide or restricted to specific
              members.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-4">
            <div className="space-y-1.5">
              <Label htmlFor="wiki-name">Name</Label>
              <Input
                id="wiki-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Engineering notes"
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wiki-vis">Visibility</Label>
              <select
                id="wiki-vis"
                value={visibility}
                onChange={(e) =>
                  setVisibility(e.target.value as WikiVisibility)
                }
                className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
              >
                <option value="org_wide">
                  Workspace-wide (any member can read)
                </option>
                <option value="private">
                  Private (only members you invite)
                </option>
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || busy}>
              {busy ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
