"use client";

import {
  ArrowRight,
  Maximize2,
  Minimize2,
  Share2,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { QACard } from "@/components/share/qa-card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { BookmarkDetailOut } from "@/lib/api/types";
import { cn, formatRelative } from "@/lib/utils";

import { deriveTitle } from "./derive-title";

/** Full-answer view for a bookmark — windowed or fullscreen, with QACard. */
export function BookmarkDetailDialog({
  bookmark,
  currentUserId,
  sharing,
  onClose,
  onRequestDelete,
  onRequestShare,
}: {
  bookmark: BookmarkDetailOut | null;
  currentUserId: string;
  sharing: boolean;
  onClose: () => void;
  onRequestDelete: (b: BookmarkDetailOut) => void;
  onRequestShare: (b: BookmarkDetailOut) => void;
}) {
  const open = bookmark !== null;
  const isOwner = bookmark?.session_owner_id === currentUserId;
  const [expanded, setExpanded] = useState(false);

  // Reset to windowed mode whenever the dialog reopens with a new bookmark —
  // surprise full-screen on next open would be jarring.
  useEffect(() => {
    if (!open) setExpanded(false);
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        hideClose
        // Suppress Radix's default "focus the first focusable child" on open —
        // it was lighting up the maximize button with a ring as soon as the
        // user opened a card. Esc/Tab still work; keyboard users can Tab in.
        onOpenAutoFocus={(e) => e.preventDefault()}
        className={cn(
          "flex flex-col overflow-hidden p-0 gap-0 transition-[max-width,max-height,border-radius] duration-200",
          expanded
            ? // Fullscreen — override the centered defaults from dialog.tsx.
              "inset-0 left-0 top-0 translate-x-0 translate-y-0 max-w-none w-screen h-dvh rounded-none border-0"
            : "max-w-3xl max-h-[85vh]"
        )}
      >
        <DialogHeader className="flex flex-row items-start justify-between gap-3 border-b border-border px-5 py-4 sm:px-6">
          <div className="min-w-0 flex-1">
            <DialogTitle className="flex items-center gap-2 text-base font-semibold">
              <Sparkles className="size-4 shrink-0 text-primary" />
              <span className="truncate">
                {bookmark ? deriveTitle(bookmark.user_message.content) : ""}
              </span>
            </DialogTitle>
            {bookmark && (
              <p className="mt-1 text-xs text-muted-foreground">
                Saved {formatRelative(bookmark.created_at)}
              </p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <TooltipProvider delayDuration={200}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={() => setExpanded((v) => !v)}
                    aria-label={expanded ? "Exit fullscreen" : "Fullscreen"}
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                  >
                    {expanded ? (
                      <Minimize2 className="size-4" />
                    ) : (
                      <Maximize2 className="size-4" />
                    )}
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  {expanded ? "Exit fullscreen (Esc)" : "Fullscreen"}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <DialogClose
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              aria-label="Close"
            >
              <X className="size-4" />
            </DialogClose>
          </div>
        </DialogHeader>

        <div
          className={cn(
            "overflow-y-auto",
            expanded
              ? "flex-1 px-5 py-5 sm:px-8 sm:py-7"
              : "max-h-[60vh] px-5 py-5 sm:px-6"
          )}
        >
          {bookmark && (
            <div className={cn(expanded && "mx-auto w-full max-w-3xl")}>
              <QACard
                density="compact"
                note={bookmark.note}
                userMessage={bookmark.user_message}
                assistantMessage={bookmark.assistant_message}
                className="border-0 shadow-none p-0"
              />
            </div>
          )}
        </div>

        {bookmark && (
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border bg-muted/30 px-5 py-3 sm:px-6">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onRequestDelete(bookmark)}
              className="text-muted-foreground hover:text-destructive"
            >
              <Trash2 />
              Remove
            </Button>
            <div className="flex items-center gap-2">
              {isOwner && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={sharing}
                  onClick={() => onRequestShare(bookmark)}
                >
                  <Share2 />
                  {sharing ? "Sharing…" : "Share"}
                </Button>
              )}
              {isOwner && (
                <Button asChild size="sm">
                  <Link href={`/chat/${bookmark.session_id}`}>
                    Open conversation
                    <ArrowRight />
                  </Link>
                </Button>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
