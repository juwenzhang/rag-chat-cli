"use client";

import { MessageCircle, Share2, Trash2 } from "lucide-react";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { BookmarkDetailOut } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { deriveTitle } from "./derive-title";

/**
 * Compact preview card — title is derived from the user's question, body
 * shows a clamped excerpt of the answer with a bottom-fade mask so the
 * truncation reads as intentional rather than abrupt.
 *
 * The card is a `div` (not a `button`) so it can host nested action
 * buttons in the top-right corner without nesting button elements.
 * Click/Enter/Space on the card opens the detail dialog; nested icon
 * buttons stop propagation so they fire their own handler instead.
 */
export function BookmarkPreviewCard({
  bookmark,
  isOwner,
  sharing,
  onOpen,
  onShare,
  onDelete,
}: {
  bookmark: BookmarkDetailOut;
  isOwner: boolean;
  sharing: boolean;
  onOpen: () => void;
  onShare: () => void;
  onDelete: () => void;
}) {
  const title = deriveTitle(bookmark.user_message.content);
  const body = bookmark.assistant_message.content;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      className={cn(
        "group relative flex h-64 w-full flex-col overflow-hidden rounded-xl",
        "border border-border bg-card p-4 text-left cursor-pointer",
        "transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md",
        "focus-visible:border-primary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
      )}
    >
      <h3 className="line-clamp-2 text-[15px] font-semibold leading-snug text-foreground">
        {title}
      </h3>

      {bookmark.note && (
        <p className="mt-1.5 line-clamp-1 text-[11px] font-medium text-primary">
          {bookmark.note}
        </p>
      )}

      <p className="mt-2 flex-1 overflow-hidden whitespace-pre-wrap break-words text-[13px] leading-6 text-muted-foreground">
        {body}
      </p>

      {/* Bottom fade mask — uses ::after-like overlay to soften the truncation. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-card via-card/90 to-transparent"
      />

      {/* Hover-revealed actions (top-right). They're always rendered for
          keyboard users but only fade in on hover/focus to keep the card
          surface calm at rest. */}
      <div
        className={cn(
          "absolute right-2 top-2 flex items-center gap-0.5 rounded-md border border-border/60 bg-background/85 p-0.5 shadow-sm backdrop-blur",
          "opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <TooltipProvider delayDuration={200}>
          {isOwner && (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label="Share this Q&A"
                  disabled={sharing}
                  onClick={(e) => {
                    e.stopPropagation();
                    onShare();
                  }}
                  className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
                >
                  <Share2 className="size-3.5" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                {sharing ? "Creating link…" : "Share"}
              </TooltipContent>
            </Tooltip>
          )}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label="Remove bookmark"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete();
                }}
                className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
              >
                <Trash2 className="size-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Remove</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      {/* Chat bubble corner anchor — visual cue that this is a conversation. */}
      <div className="absolute bottom-3 right-3 flex size-7 items-center justify-center rounded-full bg-muted/70 text-muted-foreground transition-colors group-hover:bg-primary/15 group-hover:text-primary">
        <MessageCircle className="size-3.5" />
      </div>
    </div>
  );
}
