"use client";

import { BookOpen, ChevronDown } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import type { UIMessage } from "../types";
import { cn } from "@/lib/utils";

/** Collapsible "Retrieved N sources" panel shown above a RAG answer. */
export function RetrievalBlock({
  hits,
}: {
  hits: NonNullable<UIMessage["retrieval"]>;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <BookOpen className="size-3.5" />
        <span>
          Retrieved <strong className="text-foreground">{hits.length}</strong>{" "}
          source{hits.length === 1 ? "" : "s"}
        </span>
        <ChevronDown
          className={cn("size-3.5 transition-transform", open && "rotate-180")}
        />
      </button>
      {open && (
        <ul className="mt-2 flex flex-col gap-2 rounded-lg border border-border bg-card p-3">
          {hits.map((h, i) => (
            <li
              key={`${h.chunk_id}-${i}`}
              className="border-l-2 border-primary/40 pl-3 text-xs"
            >
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px]">
                  [{i + 1}]
                </Badge>
                <span className="truncate font-medium">
                  {h.title || h.document_id.slice(0, 8)}
                </span>
                <span className="ml-auto text-[10px] text-muted-foreground">
                  {h.score.toFixed(3)}
                </span>
              </div>
              <p className="mt-1 line-clamp-3 text-muted-foreground">
                {h.content}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
