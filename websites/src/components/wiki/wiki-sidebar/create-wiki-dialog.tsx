"use client";

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
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/browser";
import type { WikiOut, WikiVisibility } from "@/lib/api/types";

/** New-wiki dialog — name + visibility, posts to the active workspace. */
export function CreateWikiDialog({
  open,
  onOpenChange,
  orgId,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  orgId: string;
  onCreated: (w: WikiOut) => void;
}) {
  const [name, setName] = useState("");
  const [visibility, setVisibility] = useState<WikiVisibility>("org_wide");
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      const wiki = await api.orgs.createWiki(orgId, {
        name: name.trim(),
        visibility,
      });
      toast.success("Wiki created");
      setName("");
      setVisibility("org_wide");
      onOpenChange(false);
      onCreated(wiki);
    } catch (err) {
      toast.error((err as Error).message || "Failed to create wiki");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>New wiki</DialogTitle>
            <DialogDescription>
              A wiki is a named knowledge base inside this workspace. Its
              pages can be shared org-wide or restricted to specific
              members.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-4">
            <div className="space-y-1.5">
              <Label htmlFor="wiki-name">Name</Label>
              <Input
                id="wiki-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Engineering notes"
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wiki-vis">Visibility</Label>
              <select
                id="wiki-vis"
                value={visibility}
                onChange={(e) =>
                  setVisibility(e.target.value as WikiVisibility)
                }
                className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
              >
                <option value="org_wide">
                  Workspace-wide (any member can read)
                </option>
                <option value="private">
                  Private (only members you invite)
                </option>
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || busy}>
              {busy ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
