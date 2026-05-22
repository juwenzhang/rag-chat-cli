"use client";

import { Book, FileText, Lock, Plus } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { DocumentOut, WikiOut } from "@/lib/api/shared/types";

export interface WikiLibrarySectionCopy {
  wikis: string;
  newWiki: string;
  noWikis: string;
  newPage: string;
  newPageIn: (name: string) => string;
  documentLibrary: string;
  newDocument: string;
  noDocuments: string;
  untitled: string;
  viewAllDocuments: (count: number) => string;
}

export function WikiLibrarySection({
  wikis,
  documents,
  documentTitleOverrides,
  canCreateWiki,
  copy,
  onCreateWiki,
  onCreatePage,
  onCreateDocument,
}: {
  wikis: WikiOut[];
  documents: DocumentOut[];
  documentTitleOverrides: Record<string, string>;
  canCreateWiki: boolean;
  copy: WikiLibrarySectionCopy;
  onCreateWiki: () => void;
  onCreatePage: (wiki: WikiOut) => void;
  onCreateDocument: () => void;
}) {
  return (
    <ScrollArea className="flex-1">
      <div className="px-3 py-4">
        <WikiList
          wikis={wikis}
          canCreateWiki={canCreateWiki}
          copy={copy}
          onCreateWiki={onCreateWiki}
          onCreatePage={onCreatePage}
        />
        <div className="my-3 border-t border-border" />
        <DocumentList
          documents={documents}
          titleOverrides={documentTitleOverrides}
          copy={copy}
          onCreateDocument={onCreateDocument}
        />
      </div>
    </ScrollArea>
  );
}

function WikiList({
  wikis,
  canCreateWiki,
  copy,
  onCreateWiki,
  onCreatePage,
}: {
  wikis: WikiOut[];
  canCreateWiki: boolean;
  copy: WikiLibrarySectionCopy;
  onCreateWiki: () => void;
  onCreatePage: (wiki: WikiOut) => void;
}) {
  return (
    <>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          {copy.wikis}
        </p>
        {canCreateWiki && (
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onCreateWiki}
            aria-label={copy.newWiki}
            className="size-5"
          >
            <Plus className="size-3" />
          </Button>
        )}
      </div>
      {wikis.length === 0 ? (
        <p className="py-6 text-xs text-muted-foreground">{copy.noWikis}</p>
      ) : (
        <ul className="flex flex-col gap-0.5">
          {wikis.map((wiki) => (
            <li key={wiki.id} className="group flex items-center">
              <Link
                href={`/wiki/${wiki.id}`}
                className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent"
              >
                <Book className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="flex-1 truncate">{wiki.name}</span>
                {wiki.visibility === "private" && (
                  <Lock className="size-3 shrink-0 text-muted-foreground" />
                )}
              </Link>
              {wiki.role !== "viewer" && (
                <TooltipProvider delayDuration={200}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        className="size-6 shrink-0 opacity-0 group-hover:opacity-100"
                        onClick={() => onCreatePage(wiki)}
                        aria-label={copy.newPage}
                      >
                        <Plus className="size-3" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="right">
                      {copy.newPageIn(wiki.name)}
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function DocumentList({
  documents,
  titleOverrides,
  copy,
  onCreateDocument,
}: {
  documents: DocumentOut[];
  titleOverrides: Record<string, string>;
  copy: WikiLibrarySectionCopy;
  onCreateDocument: () => void;
}) {
  return (
    <>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          {copy.documentLibrary}
        </p>
        <Button
          variant="ghost"
          size="icon-sm"
          className="size-5"
          onClick={onCreateDocument}
          aria-label={copy.newDocument}
        >
          <Plus className="size-3" />
        </Button>
      </div>
      {documents.length === 0 ? (
        <p className="py-4 text-center text-xs text-muted-foreground">
          {copy.noDocuments}
        </p>
      ) : (
        <ul className="flex flex-col gap-0.5">
          {documents.slice(0, 10).map((document) => (
            <li key={document.id}>
              <Link
                href={`/wiki/documents/${document.id}`}
                className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-accent"
              >
                <FileText className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="flex-1 truncate">
                  {titleOverrides[document.id] ?? (document.title || copy.untitled)}
                </span>
              </Link>
            </li>
          ))}
          {documents.length > 10 && (
            <li>
              <Link
                href="/wiki/documents"
                className="px-2 py-1 text-xs text-primary hover:underline"
              >
                {copy.viewAllDocuments(documents.length)}
              </Link>
            </li>
          )}
        </ul>
      )}
    </>
  );
}
