"use client";

import { Clock, Cpu, Hash, MessageSquare, Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import { Markdown } from "@/components/chat/markdown";
import { Card } from "@/components/ui/card";
import type { SharedMessage } from "@/lib/api/types";
import { cn, formatRelative } from "@/lib/utils";

export interface QACardProps {
  userMessage: SharedMessage;
  assistantMessage: SharedMessage;
  /** Shown above the Q&A — typically a date or "Bookmarked X ago". */
  caption?: ReactNode;
  /** Trailing actions row (Continue/Fork/Delete buttons). */
  footer?: ReactNode;
  /** Optional free-text note (bookmarks page renders this). */
  note?: string | null;
  /** Tighter padding for list views. */
  density?: "comfortable" | "compact";
  className?: string;
}

/**
 * One Q&A pair rendered as a self-contained card. Used by both the public
 * share page (``/share/[token]``) and the private bookmarks page
 * (``/bookmarks``) so the visual shape stays identical regardless of source.
 */
export function QACard({
  userMessage,
  assistantMessage,
  caption,
  footer,
  note,
  density = "comfortable",
  className,
}: QACardProps) {
  const pad = density === "compact" ? "p-4 sm:p-5" : "p-5 sm:p-7";
  return (
    <Card
      className={cn(
        "relative flex flex-col gap-4 border-border/70 bg-card/80 shadow-sm",
        pad,
        className
      )}
    >
      {caption && (
        <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
          {caption}
        </div>
      )}

      {note && (
        <div className="rounded-md border border-primary/20 bg-primary/5 px-3 py-2 text-sm text-foreground/90">
          <span className="mr-1.5 text-[10px] font-medium uppercase tracking-wider text-primary">
            Note
          </span>
          {note}
        </div>
      )}

      {/* User question */}
      <div className="flex gap-3 sm:gap-4">
        <div
          aria-hidden
          className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-user-bubble text-user-bubble-foreground"
        >
          <MessageSquare className="size-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Question
          </div>
          <div className="mt-1.5 whitespace-pre-wrap break-words text-[15px] leading-7 text-foreground">
            {userMessage.content}
          </div>
        </div>
      </div>

      {/* Assistant answer */}
      <div className="flex gap-3 sm:gap-4">
        <div
          aria-hidden
          className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg border border-border bg-card shadow-sm"
        >
          <Sparkles className="size-3.5 text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Answer
          </div>
          <div className="mt-1.5">
            <Markdown>{assistantMessage.content}</Markdown>
          </div>
          <AnswerFooter message={assistantMessage} />
        </div>
      </div>

      {footer && (
        <div className="-mx-1 mt-1 flex flex-wrap items-center gap-2 border-t border-border/50 pt-4">
          {footer}
        </div>
      )}
    </Card>
  );
}

function AnswerFooter({ message }: { message: SharedMessage }) {
  const parts: ReactNode[] = [];
  if (message.model || message.provider_name) {
    parts.push(
      <span key="model" className="inline-flex items-center gap-1">
        <Cpu className="size-3" />
        {message.provider_name && message.model
          ? `${message.provider_name} · ${message.model}`
          : message.model || message.provider_name}
      </span>
    );
  }
  if (typeof message.tokens === "number") {
    parts.push(
      <span key="tok" className="inline-flex items-center gap-1">
        <Hash className="size-3" />
        {formatTokens(message.tokens)} tok
      </span>
    );
  }
  parts.push(
    <span key="when" className="inline-flex items-center gap-1">
      <Clock className="size-3" />
      {formatRelative(message.created_at)}
    </span>
  );
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
      {parts}
    </div>
  );
}

function formatTokens(n: number): string {
  if (n < 1000) return String(n);
  return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`;
}
