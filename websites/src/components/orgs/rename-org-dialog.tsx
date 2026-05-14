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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/browser";
import type { OrgOut } from "@/lib/api/types";

/** Rename-workspace dialog. Open when `org` is non-null. */
export function RenameOrgDialog({
  org,
  onClose,
  onRenamed,
}: {
  org: OrgOut | null;
  onClose: () => void;
  onRenamed: () => void;
}) {
  const [name, setName] = useState(org?.name ?? "");
  const [busy, setBusy] = useState(false);

  // Re-seed the input when a different org opens the dialog.
  useEffect(() => {
    setName(org?.name ?? "");
  }, [org]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!org || !name.trim() || busy || name.trim() === org.name) {
      onClose();
      return;
    }
    setBusy(true);
    try {
      await api.orgs.update(org.id, { name: name.trim() });
      toast.success("Workspace renamed");
      onRenamed();
      onClose();
    } catch (err) {
      toast.error((err as Error).message || "Failed to rename");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={org !== null} onOpenChange={(n) => !n && onClose()}>
      <DialogContent className="max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Rename workspace</DialogTitle>
            <DialogDescription>
              Workspace slug stays the same so existing URLs keep working.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label htmlFor="rename-name" className="sr-only">
              Name
            </Label>
            <Input
              id="rename-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || busy}>
              {busy ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
