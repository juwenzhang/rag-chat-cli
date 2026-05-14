"use client";

import {
  Bookmark,
  BookmarkCheck,
  Check,
  Copy,
  RefreshCw,
  Share2,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ShareDialog } from "@/components/share/share-dialog";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { api } from "@/lib/api/browser";
import type { ShareOut } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** Hover-revealed Copy / Share / Bookmark / Regenerate row under an answer. */
export function ActionRow({
  text,
  messageId,
  userMessageId,
  onRegenerate,
}: {
  text: string;
  /** Server id of the assistant message — present once persisted. */
  messageId?: string;
  /** Server id of the preceding user message — paired with ``messageId``. */
  userMessageId?: string;
  /** Set by ChatView on the trailing assistant turn when re-streaming
   *  is allowed (no in-flight stream, message persisted). */
  onRegenerate?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [share, setShare] = useState<ShareOut | null>(null);
  const [sharing, setSharing] = useState(false);
  const [bookmarked, setBookmarked] = useState(false);
  const [bookmarking, setBookmarking] = useState(false);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      toast.success("Copied");
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Failed to copy");
    }
  };

  const onShare = async () => {
    if (!messageId || !userMessageId) return;
    setSharing(true);
    try {
      const data = await api.shares.create({
        user_message_id: userMessageId,
        assistant_message_id: messageId,
      });
      setShare(data);
      setShareOpen(true);
    } catch {
      toast.error("Failed to create share link");
    } finally {
      setSharing(false);
    }
  };

  const onBookmark = async () => {
    if (!messageId || !userMessageId) return;
    setBookmarking(true);
    try {
      await api.bookmarks.create({
        user_message_id: userMessageId,
        assistant_message_id: messageId,
      });
      setBookmarked(true);
      toast.success("Saved to bookmarks");
    } catch {
      toast.error("Failed to bookmark");
    } finally {
      setBookmarking(false);
    }
  };

  const canPersist = !!messageId && !!userMessageId;

  return (
    <>
      <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={onCopy}
                className="size-7 text-muted-foreground hover:text-foreground"
                aria-label="Copy"
              >
                {copied ? <Check /> : <Copy />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{copied ? "Copied" : "Copy"}</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={onShare}
                disabled={!canPersist || sharing}
                className="size-7 text-muted-foreground hover:text-foreground"
                aria-label="Share"
              >
                <Share2 />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {canPersist ? "Share this Q&A" : "Available after refresh"}
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={onBookmark}
                disabled={!canPersist || bookmarking || bookmarked}
                className={cn(
                  "size-7 text-muted-foreground hover:text-foreground",
                  bookmarked && "text-primary"
                )}
                aria-label="Bookmark"
              >
                {bookmarked ? <BookmarkCheck /> : <Bookmark />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {bookmarked
                ? "Saved"
                : canPersist
                  ? "Save to bookmarks"
                  : "Available after refresh"}
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                disabled={!onRegenerate}
                onClick={onRegenerate}
                className="size-7 text-muted-foreground hover:text-foreground"
                aria-label="Regenerate"
              >
                <RefreshCw />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {onRegenerate ? "Regenerate this answer" : "Regenerate"}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <ShareDialog
        open={shareOpen}
        onOpenChange={setShareOpen}
        share={share}
        onRevoked={() => {
          setShare(null);
          setShareOpen(false);
        }}
      />
    </>
  );
}
