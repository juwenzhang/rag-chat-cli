"use client";

import { Book, ExternalLink } from "lucide-react";
import Link from "next/link";

import { Markdown } from "@/components/chat/markdown";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import type { WikiPageSharePublicOut } from "@/lib/api/types";
import { formatRelative } from "@/lib/utils";

interface Props {
  share: WikiPageSharePublicOut;
}

export function WikiShareView({ share }: Props) {
  return (
    <main className="relative min-h-dvh bg-background">
      {/* Brand stripe */}
      <header className="sticky top-0 z-10 border-b border-border/60 bg-background/85 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex size-7 items-center justify-center rounded-md bg-brand-gradient text-white shadow shadow-primary/20">
              <span className="text-xs font-bold">R</span>
            </div>
            <span className="font-semibold tracking-tight">lhx-rag</span>
          </Link>
          <ThemeToggle />
        </div>
      </header>

      <div className="mx-auto w-full max-w-3xl px-4 pb-16 pt-8 sm:px-6 sm:pt-12">
        {/* Title block */}
        <div className="mb-6 space-y-2 sm:mb-8">
          <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-primary">
            <Book className="size-3.5" />
            {share.wiki_name}
          </div>
          <h1 className="text-2xl font-semibold leading-tight tracking-tight sm:text-3xl">
            {share.page_title}
          </h1>
          <p className="text-sm text-muted-foreground">
            Shared {formatRelative(share.created_at)}
            {share.shared_by_display_name &&
              ` by ${share.shared_by_display_name}`}
          </p>
        </div>

        {/* Page content — rendered as markdown */}
        <Markdown className="prose prose-neutral dark:prose-invert max-w-none">
          {share.page_body}
        </Markdown>

        <footer className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pt-6 text-xs text-muted-foreground">
          <span>
            Powered by{" "}
            <span className="font-medium text-foreground">lhx-rag</span> — a
            self-hosted AI runner.
          </span>
          <Link
            href="/"
            className="inline-flex items-center gap-1 hover:text-foreground"
          >
            Learn more
            <ExternalLink className="size-3" />
          </Link>
        </footer>
      </div>
    </main>
  );
}
