"use client";

import {
  ArrowRight,
  Maximize2,
  MessageCircle,
  Minimize2,
  Search,
  Share2,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { QACard } from "@/components/share/qa-card";
import { ShareDialog } from "@/components/share/share-dialog";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { BookmarkDetailOut, ShareOut } from "@/lib/api/types";
import { cn, formatRelative } from "@/lib/utils";

interface Props {
  currentUserId: string;
  bookmarks: BookmarkDetailOut[];
}

export function BookmarksPageClient({ currentUserId, bookmarks }: Props) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [pendingDelete, setPendingDelete] = useState<BookmarkDetailOut | null>(
    null
  );
  const [opened, setOpened] = useState<BookmarkDetailOut | null>(null);
  const [share, setShare] = useState<ShareOut | null>(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [sharingId, setSharingId] = useState<string | null>(null);

  // Owner-only action: only the user that authored the underlying session
  // can mint a share for it. We hide the share button on bookmarks that
  // point at someone else's session (shouldn't happen yet, but the API
  // model already permits cross-user reads via fork, so guard anyway).
  const onShare = async (b: BookmarkDetailOut) => {
    if (b.session_owner_id !== currentUserId) return;
    if (sharingId) return;
    setSharingId(b.id);
    try {
      const res = await fetch("/api/shares", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_message_id: b.user_message_id,
          assistant_message_id: b.assistant_message_id,
        }),
      });
      if (!res.ok) {
        toast.error("Failed to create share link");
        return;
      }
      const created = (await res.json()) as ShareOut;
      setShare(created);
      setShareOpen(true);
    } finally {
      setSharingId(null);
    }
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return bookmarks;
    return bookmarks.filter((b) => {
      return (
        b.user_message.content.toLowerCase().includes(q) ||
        b.assistant_message.content.toLowerCase().includes(q) ||
        (b.note ?? "").toLowerCase().includes(q)
      );
    });
  }, [bookmarks, query]);

  const onDelete = async () => {
    if (!pendingDelete) return;
    const res = await fetch(`/api/bookmarks/${pendingDelete.id}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      toast.error("Failed to remove bookmark");
      throw new Error("delete failed");
    }
    toast.success("Bookmark removed");
    // If the dialog showed this bookmark, close it.
    if (opened?.id === pendingDelete.id) setOpened(null);
    router.refresh();
  };

  return (
    <div className="mx-auto w-full max-w-7xl px-4 pb-16 pt-6 sm:px-6 sm:pt-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1.5">
          <p className="text-[11px] font-medium uppercase tracking-wider text-primary">
            Bookmarks
          </p>
          <h1 className="text-2xl font-semibold leading-tight tracking-tight sm:text-3xl">
            收藏夹
          </h1>
          <p className="text-sm text-muted-foreground">
            {bookmarks.length} saved · click a card to open the full answer
          </p>
        </div>
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search bookmarks…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-9"
          />
        </div>
      </header>

      {bookmarks.length === 0 ? (
        <EmptyState />
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-card/40 p-10 text-center text-sm text-muted-foreground">
          No bookmarks match <span className="font-medium">{query}</span>.
        </div>
      ) : (
        <ul
          className={cn(
            "grid gap-3 sm:gap-4",
            "grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5"
          )}
        >
          {filtered.map((b) => {
            const isOwner = b.session_owner_id === currentUserId;
            return (
              <li key={b.id}>
                <BookmarkPreviewCard
                  bookmark={b}
                  isOwner={isOwner}
                  sharing={sharingId === b.id}
                  onOpen={() => setOpened(b)}
                  onShare={() => onShare(b)}
                  onDelete={() => setPendingDelete(b)}
                />
              </li>
            );
          })}
        </ul>
      )}

      <BookmarkDetailDialog
        bookmark={opened}
        currentUserId={currentUserId}
        sharing={opened ? sharingId === opened.id : false}
        onClose={() => setOpened(null)}
        onRequestDelete={(b) => setPendingDelete(b)}
        onRequestShare={(b) => onShare(b)}
      />

      <ShareDialog
        open={shareOpen}
        onOpenChange={setShareOpen}
        share={share}
        onRevoked={() => {
          setShare(null);
          setShareOpen(false);
        }}
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Remove this bookmark?"
        description="The conversation itself stays — only the bookmark goes away."
        confirmLabel="Remove"
        destructive
        onConfirm={onDelete}
      />
    </div>
  );
}

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
function BookmarkPreviewCard({
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

function BookmarkDetailDialog({
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

function EmptyState() {
  return (
    <div className="rounded-xl border border-dashed border-border bg-card/40 p-10 text-center">
      <p className="text-sm font-medium">No bookmarks yet</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Open any answer in chat and click the bookmark icon to save it here.
      </p>
    </div>
  );
}

/**
 * Pull a card-sized title out of the question text. Strips leading
 * markdown punctuation, collapses whitespace, and caps at ~32 chars so it
 * never wraps past two lines in the preview card.
 */
function deriveTitle(question: string): string {
  const cleaned = question
    .replace(/^[\s#>*\-]+/, "")
    .split(/\n+/)[0]
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return "Untitled question";
  if (cleaned.length <= 32) return cleaned;
  return cleaned.slice(0, 30).trimEnd() + "…";
}
