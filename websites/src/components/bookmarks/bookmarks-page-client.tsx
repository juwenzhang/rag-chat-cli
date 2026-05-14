"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { ShareDialog } from "@/components/share/share-dialog";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import type { BookmarkDetailOut, ShareOut } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { BookmarkDetailDialog } from "./bookmark-detail-dialog";
import { BookmarkEmptyState } from "./bookmark-empty-state";
import { BookmarkPreviewCard } from "./bookmark-preview-card";

interface Props {
  currentUserId: string;
  bookmarks: BookmarkDetailOut[];
}

/** Bookmarks page — searchable grid of saved Q&As, preview + detail dialog. */
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
      const created = await api.shares.create({
        user_message_id: b.user_message_id,
        assistant_message_id: b.assistant_message_id,
      });
      setShare(created);
      setShareOpen(true);
    } catch {
      toast.error("Failed to create share link");
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
    try {
      await api.bookmarks.remove(pendingDelete.id);
    } catch (err) {
      toast.error("Failed to remove bookmark");
      throw err;
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
        <BookmarkEmptyState />
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
