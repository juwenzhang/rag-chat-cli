"use client";

import { Check, Copy, Link2, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import type { WikiPageShareOut } from "@/lib/api/types";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pageId: string;
  pageTitle: string;
}

/**
 * Dialog that creates (or retrieves) a public share link for a wiki page.
 *
 * On open it calls POST /wiki-pages/:id/share (get-or-create) and displays
 * the resulting URL. The user can copy or revoke.
 */
export function WikiPageShareDialog({
  open,
  onOpenChange,
  pageId,
  pageTitle,
}: Props) {
  const [share, setShare] = useState<WikiPageShareOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [revoking, setRevoking] = useState(false);

  const createOrFetch = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.wikiPages.createShare(pageId);
      setShare(result);
    } catch {
      toast.error("Failed to create share link");
    } finally {
      setLoading(false);
    }
  }, [pageId]);

  useEffect(() => {
    if (open && !share) {
      void createOrFetch();
    }
    // Reset state when dialog closes.
    if (!open) {
      setShare(null);
      setCopied(false);
    }
  }, [open, share, createOrFetch]);

  const shareUrl =
    share && typeof window !== "undefined"
      ? `${window.location.origin}/share/wiki/${share.token}`
      : "";

  const onCopy = async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      toast.success("Link copied");
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Failed to copy");
    }
  };

  const onRevoke = async () => {
    if (!share) return;
    setRevoking(true);
    try {
      await api.wikiPageShares.remove(share.token);
      toast.success("Share link revoked");
      setShare(null);
      onOpenChange(false);
    } catch {
      toast.error("Failed to revoke");
    } finally {
      setRevoking(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Link2 className="size-4 text-primary" />
            Share this page
          </DialogTitle>
          <DialogDescription>
            Anyone with this link can read &ldquo;{pageTitle}&rdquo;. They
            won&apos;t need to sign in or be a workspace member.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          </div>
        ) : share ? (
          <div className="space-y-3">
            <div className="flex gap-2">
              <Input
                value={shareUrl}
                readOnly
                className="font-mono text-xs"
              />
              <Button onClick={onCopy} variant="outline">
                {copied ? <Check /> : <Copy />}
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Revoke any time — the link will 404 immediately.
            </p>
          </div>
        ) : null}

        <DialogFooter>
          {share && (
            <Button
              variant="ghost"
              onClick={onRevoke}
              disabled={revoking}
              className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            >
              {revoking ? "Revoking…" : "Revoke link"}
            </Button>
          )}
          <Button onClick={() => onOpenChange(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
