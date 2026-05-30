"use client";

import { BookOpen, ChevronDown, ExternalLink, PanelRightOpen } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

import type { UIMessage } from "../types";

/** Collapsible "Retrieved N sources" panel shown above a RAG answer. */
export function RetrievalBlock({ hits }: { hits: NonNullable<UIMessage["retrieval"]> }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <BookOpen className="size-3.5" />
        <span>
          Retrieved <strong className="text-foreground">{hits.length}</strong> source
          {hits.length === 1 ? "" : "s"}
        </span>
        <ChevronDown
          className={cn("size-3.5 transition-transform", open && "rotate-180")}
        />
      </button>

      <Dialog>
        <DialogTrigger asChild>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <PanelRightOpen className="size-3.5" />
            Sources panel
          </button>
        </DialogTrigger>
        <DialogContent className="right-0 top-0 left-auto h-dvh max-h-dvh w-full max-w-xl translate-x-0 translate-y-0 rounded-none border-y-0 border-r-0 sm:p-6">
          <DialogHeader>
            <DialogTitle>Answer sources</DialogTitle>
            <DialogDescription>
              Documents used to ground this answer. Open a document to inspect the source
              material.
            </DialogDescription>
          </DialogHeader>
          <SourceList hits={hits} expanded />
        </DialogContent>
      </Dialog>

      {open && <SourceList hits={hits} />}
    </div>
  );
}

function SourceList({
  hits,
  expanded = false,
}: {
  hits: NonNullable<UIMessage["retrieval"]>;
  expanded?: boolean;
}) {
  return (
    <ul
      className={cn(
        "flex w-full flex-col gap-2 rounded-lg border border-border bg-card p-3",
        expanded && "max-h-[calc(100dvh-11rem)] overflow-y-auto"
      )}
    >
      {hits.map((h, i) => (
        <li
          key={`${h.chunk_id}-${i}`}
          className="border-l-2 border-primary/40 pl-3 text-xs"
        >
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[10px]">
              [{i + 1}]
            </Badge>
            <Link
              href={`/wiki/documents/${h.document_id}`}
              className="inline-flex min-w-0 items-center gap-1 truncate font-medium text-foreground hover:underline"
            >
              <span className="truncate">{h.title || h.document_id.slice(0, 8)}</span>
              <ExternalLink className="size-3 shrink-0 text-muted-foreground" />
            </Link>
            <span className="ml-auto text-[10px] text-muted-foreground">
              {h.score.toFixed(3)}
            </span>
          </div>
          {h.source && (
            <div className="mt-0.5 truncate text-[10px] text-muted-foreground">
              {h.source}
            </div>
          )}
          <p
            className={cn(
              "mt-1 text-muted-foreground",
              expanded ? "whitespace-pre-wrap" : "line-clamp-3"
            )}
          >
            {h.content}
          </p>
        </li>
      ))}
    </ul>
  );
}
