"use client";

import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { documentService, wikiPageService, wikiService } from "@/features/wiki/services/wiki-page-service";
import { useWikiStore } from "@/features/wiki/stores/wiki-store";
import type { DocumentOut, OrgOut, WikiOut, WikiPageListOut } from "@/lib/api/shared/types";
import { useI18n } from "@/lib/i18n/provider";

import { CollapsedSidebar } from "./collapsed-sidebar";
import { CreateWikiDialog } from "./create-wiki-dialog";
import { buildTree } from "./tree";
import { WikiLibrarySection } from "./wiki-library-section";
import { WikiPageSection } from "./wiki-page-section";
import { WikiSwitcher } from "./wiki-switcher";

interface Props {
  activeOrg: OrgOut;
  wikis: WikiOut[];
  activeWiki: WikiOut | null;
  pages: WikiPageListOut[];
  documents: DocumentOut[];
}

/** Two-level wiki sidebar — workspace/wiki switcher above the page tree. */
export function WikiSidebar({ activeOrg, wikis, activeWiki, pages, documents }: Props) {
  const router = useRouter();
  const { t } = useI18n();
  const params = useParams();
  const pathname = usePathname();
  const activePageId =
    typeof params.pageId === "string" ? params.pageId : null;
  const urlWikiId =
    typeof params.wikiId === "string" ? params.wikiId : null;

  const isAtRoot = pathname === "/wiki" || pathname.startsWith("/wiki/documents");
  useEffect(() => {
    if (isAtRoot && activeWiki !== null) {
      router.refresh();
      return;
    }
    if (!urlWikiId || urlWikiId === activeWiki?.id) return;
    if (!wikis.some((wiki) => wiki.id === urlWikiId)) return;
    router.refresh();
  }, [urlWikiId, activeWiki?.id, wikis, router, isAtRoot, activeWiki]);

  const query = useWikiStore((state) => state.sidebarQuery);
  const collapsed = useWikiStore((state) => state.sidebarCollapsed);
  const titleOverrides = useWikiStore((state) => state.pageTitleOverrides);
  const docTitleOverrides = useWikiStore((state) => state.documentTitleOverrides);
  const setQuery = useWikiStore((state) => state.setSidebarQuery);
  const setCollapsed = useWikiStore((state) => state.setSidebarCollapsed);
  const [creating, setCreating] = useState(false);
  const [pendingDelete, setPendingDelete] =
    useState<WikiPageListOut | null>(null);
  const [pendingWikiDelete, setPendingWikiDelete] =
    useState<WikiOut | null>(null);
  const [createWikiOpen, setCreateWikiOpen] = useState(false);

  const canEditWiki = activeWiki !== null && activeWiki.role !== "viewer";
  const orgCanCreateWiki = activeOrg.role !== "viewer";

  const effectivePages = useMemo(
    () =>
      pages.map((page) =>
        titleOverrides[page.id] != null
          ? { ...page, title: titleOverrides[page.id] }
          : page
      ),
    [pages, titleOverrides]
  );

  const tree = useMemo(() => buildTree(effectivePages), [effectivePages]);
  const searchHits = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return null;
    return effectivePages.filter((page) =>
      page.title.toLowerCase().includes(normalized)
    );
  }, [effectivePages, query]);

  const createPage = async (wikiId: string, parentId?: string) => {
    if (creating) return;
    setCreating(true);
    try {
      const page = await wikiService.createPage(
        wikiId,
        parentId ? { parent_id: parentId } : {}
      );
      router.push(`/wiki/${wikiId}/p/${page.id}`);
      router.refresh();
    } catch {
      toast.error("Failed to create page");
    } finally {
      setCreating(false);
    }
  };

  const createDocument = async () => {
    try {
      const document = await documentService.createDocument({});
      router.push(`/wiki/documents/${document.id}`);
      router.refresh();
    } catch {
      toast.error("Failed to create document");
    }
  };

  const onDeletePage = async () => {
    if (!pendingDelete) return;
    try {
      await wikiPageService.deletePage(pendingDelete.id);
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
      await wikiService.deleteWiki(pendingWikiDelete.id);
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
      <CollapsedSidebar
        canCreatePage={canEditWiki}
        creating={creating}
        onCreatePage={() => activeWiki && void createPage(activeWiki.id)}
        onExpand={() => setCollapsed(false)}
      />
    );
  }

  return (
    <aside className="hidden h-full w-64 shrink-0 flex-col border-r border-border bg-card/40 md:flex">
      <WikiSwitcher
        activeOrg={activeOrg}
        activeWiki={activeWiki}
        wikis={wikis}
        canCreateWiki={orgCanCreateWiki}
        onCollapse={() => setCollapsed(true)}
        onCreateWiki={() => setCreateWikiOpen(true)}
        onRequestDeleteWiki={setPendingWikiDelete}
      />

      {activeWiki ? (
        <WikiPageSection
          wikiId={activeWiki.id}
          pages={pages}
          tree={tree}
          searchHits={searchHits}
          query={query}
          creating={creating}
          canEdit={canEditWiki}
          activePageId={activePageId}
          copy={{
            creating: t("common.creating"),
            newPage: t("wiki.newPage"),
            pages: t("wiki.pages"),
            searchPages: t("wiki.searchPages"),
            noPages: t("wiki.noPages"),
            noMatches: t("wiki.noMatches"),
          }}
          onQueryChange={setQuery}
          onCreatePage={() => void createPage(activeWiki.id)}
          onCreateChildPage={(parentId) => void createPage(activeWiki.id, parentId)}
          onRequestDelete={setPendingDelete}
        />
      ) : (
        <WikiLibrarySection
          wikis={wikis}
          documents={documents}
          documentTitleOverrides={docTitleOverrides}
          canCreateWiki={orgCanCreateWiki}
          copy={{
            wikis: t("wiki.wikis"),
            newWiki: t("wiki.newWiki"),
            noWikis: t("wiki.noWikis"),
            newPage: t("wiki.newPage"),
            newPageIn: (name) => t("wiki.newPageIn", { name }),
            documentLibrary: t("wiki.documentLibrary"),
            newDocument: t("wiki.newDocument"),
            noDocuments: t("wiki.noDocuments"),
            untitled: t("common.untitled"),
            viewAllDocuments: (count) => t("wiki.viewAllDocuments", { count }),
          }}
          onCreateWiki={() => setCreateWikiOpen(true)}
          onCreatePage={(wiki) => void createPage(wiki.id)}
          onCreateDocument={() => void createDocument()}
        />
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
            will be removed. Child pages lose their parent and move to the root.
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
        onCreated={(wiki) => {
          router.push(`/wiki/${wiki.id}`);
          router.refresh();
        }}
      />
    </aside>
  );
}
