"use client";

import {
  BookOpen,
  ExternalLink,
  FileText,
  Globe2,
  ImageIcon,
  PanelRightOpen,
  Wrench,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { AnswerSource } from "@/lib/api/shared/types";
import { externalLinkHref } from "@/lib/external-link";
import { cn } from "@/lib/utils";

import { Markdown } from "../markdown";

const SOURCE_ICON = {
  document: FileText,
  web: Globe2,
  image: ImageIcon,
  tool: Wrench,
} satisfies Record<AnswerSource["source_type"], typeof FileText>;

export function SourcesBlock({ sources }: { sources: AnswerSource[] }) {
  const [open, setOpen] = useState(false);
  const [activeRank, setActiveRank] = useState<number | null>(null);

  if (sources.length === 0) return null;

  const openAt = (source: AnswerSource) => {
    setActiveRank(source.rank);
    setOpen(true);
  };

  return (
    <SourcesDrawerShell
      sources={sources}
      open={open}
      activeRank={activeRank}
      onOpenChange={setOpen}
    >
      <div className="flex flex-wrap items-center gap-2">
        <DialogTrigger asChild>
          <button
            type="button"
            onClick={() => setActiveRank(null)}
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <PanelRightOpen className="size-3.5" />
            <span>
              Sources <strong className="text-foreground">{sources.length}</strong>
            </span>
          </button>
        </DialogTrigger>

        <div className="flex flex-wrap gap-1.5">
          {sources.slice(0, 10).map((source, index) => (
            <button
              key={`${source.source_type}-${source.rank}-${index}`}
              type="button"
              onClick={() => openAt(source)}
              className="inline-flex h-6 items-center gap-1 rounded-full border border-border bg-card px-2 text-[11px] text-muted-foreground transition-colors hover:border-primary/40 hover:bg-accent hover:text-foreground"
              title={source.title || source.url || source.source || undefined}
            >
              [{source.rank || index + 1}]
            </button>
          ))}
        </div>
      </div>
    </SourcesDrawerShell>
  );
}

export function SourcesDrawerTrigger({
  sources,
  children,
}: {
  sources: AnswerSource[];
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  if (sources.length === 0) return null;

  return (
    <SourcesDrawerShell
      sources={sources}
      open={open}
      activeRank={null}
      onOpenChange={setOpen}
    >
      <DialogTrigger asChild>{children}</DialogTrigger>
    </SourcesDrawerShell>
  );
}

function SourcesDrawerShell({
  sources,
  open,
  activeRank,
  onOpenChange,
  children,
}: {
  sources: AnswerSource[];
  open: boolean;
  activeRank: number | null;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open || activeRank == null) return;
    const timer = window.setTimeout(() => {
      document.getElementById(sourceDomId(activeRank))?.scrollIntoView({
        block: "center",
        behavior: "smooth",
      });
    }, 80);
    return () => window.clearTimeout(timer);
  }, [activeRank, open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {children}
      <DialogContent
        className={cn(
          "right-0 top-0 left-auto flex h-dvh max-h-dvh w-full translate-x-0 translate-y-0 overflow-hidden rounded-none border-y-0 border-r-0 p-0 transition-[max-width] duration-200 sm:p-0",
          activeRank == null ? "max-w-xl" : "max-w-3xl"
        )}
      >
        <div className="flex min-h-0 w-full flex-1 flex-col">
          <DialogHeader className="border-b border-border px-5 py-4 pr-12">
            <DialogTitle>Answer sources</DialogTitle>
            <DialogDescription>
              Sources used by this answer. Click a title to open the original page or
              document.
            </DialogDescription>
          </DialogHeader>
          <SourceList sources={sources} activeRank={activeRank} />
        </div>
      </DialogContent>
    </Dialog>
  );
}

function SourceList({
  sources,
  activeRank,
}: {
  sources: AnswerSource[];
  activeRank: number | null;
}) {
  return (
    <ScrollArea className="min-h-0 flex-1">
      <ul className="flex flex-col gap-3 p-5">
        {sources.map((source, index) => (
          <SourceItem
            key={`${source.source_type}-${source.rank}-${index}`}
            source={source}
            index={index}
            active={activeRank === source.rank}
          />
        ))}
      </ul>
    </ScrollArea>
  );
}

function SourceItem({
  source,
  index,
  active,
}: {
  source: AnswerSource;
  index: number;
  active: boolean;
}) {
  const Icon = SOURCE_ICON[source.source_type] ?? BookOpen;
  const rank = source.rank || index + 1;
  const title =
    source.title || source.source || source.url || `${source.source_type} source`;

  return (
    <li
      id={sourceDomId(rank)}
      className={cn(
        "rounded-xl border border-border bg-card p-3 text-xs transition-colors",
        active && "border-primary/60 bg-primary/5 ring-1 ring-primary/30"
      )}
    >
      <div className="flex min-w-0 items-start gap-2">
        <Badge variant="outline" className="mt-0.5 text-[10px]">
          [{rank}]
        </Badge>
        <Icon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <SourceTitle source={source} title={title} />
          {(source.source || source.url) && (
            <div className="mt-1 truncate text-[10px] text-muted-foreground">
              {source.url || source.source}
            </div>
          )}
        </div>
        {source.score != null && (
          <span className="mt-0.5 shrink-0 text-[10px] text-muted-foreground">
            {source.score.toFixed(3)}
          </span>
        )}
      </div>
      {source.quote && <SourceQuote quote={source.quote} />}
    </li>
  );
}

function SourceQuote({ quote }: { quote: string }) {
  return (
    <div className="mt-2 max-h-72 overflow-auto overscroll-contain rounded-lg bg-muted/30 p-2 text-muted-foreground">
      {looksLikeMarkdown(quote) ? (
        <Markdown className="min-w-fit text-xs leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 [&_.table-wrapper]:my-2 [&_.table-wrapper]:overflow-x-auto [&_pre]:my-2 [&_pre]:max-h-48 [&_pre]:overflow-auto [&_table]:min-w-max">
          {quote}
        </Markdown>
      ) : (
        <p className="whitespace-pre-wrap wrap-break-word">{quote}</p>
      )}
    </div>
  );
}

function looksLikeMarkdown(text: string): boolean {
  return (
    /(^|\n)\s*(```|#{1,6}\s|[-*+]\s|\d+\.\s|>\s|\|.+\||```mermaid)/i.test(text) ||
    /\[[^\]]+\]\([^)]+\)|[*_]{1,2}[^*_]+[*_]{1,2}|`[^`]+`/.test(text)
  );
}

function SourceTitle({ source, title }: { source: AnswerSource; title: string }) {
  if (source.source_type === "document" && source.document_id) {
    return (
      <Link
        href={`/wiki/documents/${source.document_id}`}
        className="inline-flex min-w-0 items-center gap-1 font-medium text-foreground hover:underline"
      >
        <span className="truncate">{title}</span>
        <ExternalLink className="size-3 shrink-0 text-muted-foreground" />
      </Link>
    );
  }

  if (source.url) {
    return (
      <a
        href={externalLinkHref(source.url)}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex min-w-0 items-center gap-1 font-medium text-foreground hover:underline"
      >
        <span className="truncate">{title}</span>
        <ExternalLink className="size-3 shrink-0 text-muted-foreground" />
      </a>
    );
  }

  return <span className="min-w-0 truncate font-medium text-foreground">{title}</span>;
}

function sourceDomId(rank: number): string {
  return `answer-source-${rank}`;
}
