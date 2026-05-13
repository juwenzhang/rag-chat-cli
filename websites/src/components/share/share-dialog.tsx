"use client";

import { Check, Copy, Link2 } from "lucide-react";
import { useState } from "react";
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
import type { ShareOut } from "@/lib/api/types";

export interface ShareDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  share: ShareOut | null;
  onRevoked: () => void;
}

export function ShareDialog({
  open,
  onOpenChange,
  share,
  onRevoked,
}: ShareDialogProps) {
  const [copied, setCopied] = useState(false);
  const [revoking, setRevoking] = useState(false);

  const shareUrl =
    share && typeof window !== "undefined"
      ? `${window.location.origin}/share/${share.token}`
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
      const res = await fetch(`/api/shares/${share.token}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        toast.error("Failed to revoke");
        return;
      }
      toast.success("Share link revoked");
      onRevoked();
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
            Share this Q&amp;A
          </DialogTitle>
          <DialogDescription>
            Anyone with this link can read the question and answer. They
            can&apos;t see the rest of your conversation.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="flex gap-2">
            <Input value={shareUrl} readOnly className="font-mono text-xs" />
            <Button onClick={onCopy} variant="outline">
              {copied ? <Check /> : <Copy />}
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Revoke any time — the link will 404 immediately.
          </p>
        </div>

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={onRevoke}
            disabled={revoking}
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
          >
            {revoking ? "Revoking…" : "Revoke link"}
          </Button>
          <Button onClick={() => onOpenChange(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
