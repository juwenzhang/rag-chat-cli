"use client";

import { Plus, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { WikiPageListOut } from "@/lib/api/shared/types";

import { PageRow } from "./page-row";
import { TreeBranch } from "./tree-branch";
import type { TreeNode } from "./tree";

export function WikiPageSection({
  wikiId,
  pages,
  tree,
  searchHits,
  query,
  creating,
  canEdit,
  activePageId,
  onQueryChange,
  onCreatePage,
  onCreateChildPage,
  onRequestDelete,
}: {
  wikiId: string;
  pages: WikiPageListOut[];
  tree: TreeNode[];
  searchHits: WikiPageListOut[] | null;
  query: string;
  creating: boolean;
  canEdit: boolean;
  activePageId: string | null;
  onQueryChange: (next: string) => void;
  onCreatePage: () => void;
  onCreateChildPage: (parentId: string) => void;
  onRequestDelete: (page: WikiPageListOut) => void;
}) {
  return (
    <>
      {canEdit && (
        <div className="px-3 pt-3">
          <Button
            onClick={onCreatePage}
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
          onChange={(event) => onQueryChange(event.target.value)}
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
          <SearchResults
            wikiId={wikiId}
            results={searchHits}
            activePageId={activePageId}
            canEdit={canEdit}
            onCreateChildPage={onCreateChildPage}
            onRequestDelete={onRequestDelete}
          />
        ) : (
          <ul className="flex flex-col gap-0.5">
            {tree.map((node) => (
              <TreeBranch
                key={node.page.id}
                wikiId={wikiId}
                node={node}
                depth={0}
                activePageId={activePageId}
                canEdit={canEdit}
                onAddChild={onCreateChildPage}
                onRequestDelete={onRequestDelete}
              />
            ))}
          </ul>
        )}
      </ScrollArea>
    </>
  );
}

function SearchResults({
  wikiId,
  results,
  activePageId,
  canEdit,
  onCreateChildPage,
  onRequestDelete,
}: {
  wikiId: string;
  results: WikiPageListOut[];
  activePageId: string | null;
  canEdit: boolean;
  onCreateChildPage: (parentId: string) => void;
  onRequestDelete: (page: WikiPageListOut) => void;
}) {
  if (results.length === 0) {
    return (
      <p className="px-3 py-6 text-center text-xs text-muted-foreground">
        No matches.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-0.5">
      {results.map((page) => (
        <li key={page.id}>
          <PageRow
            wikiId={wikiId}
            page={page}
            depth={0}
            active={page.id === activePageId}
            canEdit={canEdit}
            onAddChild={() => onCreateChildPage(page.id)}
            onRequestDelete={() => onRequestDelete(page)}
          />
        </li>
      ))}
    </ul>
  );
}
