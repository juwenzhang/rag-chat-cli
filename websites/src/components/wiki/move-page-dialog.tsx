"use client";

import { useEffect, useState } from "react";
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
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/browser";
import type { WikiOut, WikiPageDetailOut } from "@/lib/api/types";

/** Dialog to move a wiki page into a different (writable) wiki. */
export function MovePageDialog({
  open,
  onOpenChange,
  currentWikiId,
  pageId,
  wikis,
  onMoved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentWikiId: string;
  pageId: string;
  wikis: WikiOut[];
  onMoved: (target: WikiPageDetailOut) => void;
}) {
  const [targetId, setTargetId] = useState(currentWikiId);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open) setTargetId(currentWikiId);
  }, [open, currentWikiId]);
  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy || targetId === currentWikiId) {
      onOpenChange(false);
      return;
    }
    setBusy(true);
    try {
      const moved = await api.wikiPages.move(pageId, {
        target_wiki_id: targetId,
      });
      toast.success("Page moved");
      onMoved(moved);
      onOpenChange(false);
    } catch (err) {
      toast.error((err as Error).message || "Failed to move");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Move to wiki</DialogTitle>
            <DialogDescription>
              The page leaves its current wiki and lands at the end of the
              destination&apos;s root list.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-4">
            <Label htmlFor="move-target">Destination wiki</Label>
            <select
              id="move-target"
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
            >
              {wikis.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                  {w.id === currentWikiId ? " (current)" : ""}
                </option>
              ))}
            </select>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={targetId === currentWikiId || busy}
            >
              {busy ? "Moving…" : "Move"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
