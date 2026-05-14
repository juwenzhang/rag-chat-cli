"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/browser";
import type { WikiOut, WikiVisibility } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** Wiki settings — name, description, visibility. */
export function WikiDetailsSection({
  wiki,
  canEdit,
  canChangeVisibility,
  onSaved,
}: {
  wiki: WikiOut;
  canEdit: boolean;
  canChangeVisibility: boolean;
  onSaved: () => void;
}) {
  const [name, setName] = useState(wiki.name);
  const [description, setDescription] = useState(wiki.description ?? "");
  const [visibility, setVisibility] = useState<WikiVisibility>(wiki.visibility);
  const [busy, setBusy] = useState(false);

  const dirty =
    name.trim() !== wiki.name ||
    (description.trim() || null) !== (wiki.description || null) ||
    visibility !== wiki.visibility;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!dirty || busy) return;
    setBusy(true);
    try {
      await api.wikis.update(wiki.id, {
        name: name.trim() !== wiki.name ? name.trim() : undefined,
        description:
          (description.trim() || null) !== (wiki.description || null)
            ? description.trim() || null
            : undefined,
        visibility: visibility !== wiki.visibility ? visibility : undefined,
      });
      toast.success("Saved");
      onSaved();
    } catch (err) {
      toast.error((err as Error).message || "Failed to save");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={onSubmit}
      className={cn(
        "mb-8 space-y-4 rounded-xl border border-border bg-card p-5",
        !canEdit && "opacity-80"
      )}
    >
      <h2 className="text-base font-semibold">Details</h2>
      <div className="space-y-1.5">
        <Label htmlFor="wiki-name">Name</Label>
        <Input
          id="wiki-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          readOnly={!canEdit}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="wiki-desc">Description</Label>
        <Textarea
          id="wiki-desc"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          readOnly={!canEdit}
          rows={2}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="wiki-vis">Visibility</Label>
        <select
          id="wiki-vis"
          value={visibility}
          onChange={(e) => setVisibility(e.target.value as WikiVisibility)}
          disabled={!canChangeVisibility}
          className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm disabled:opacity-60"
        >
          <option value="org_wide">
            Workspace-wide — any workspace member can read
          </option>
          <option value="private">Private — only invited members</option>
        </select>
        {!canChangeVisibility && (
          <p className="text-[11px] text-muted-foreground">
            Only the workspace owner can change visibility.
          </p>
        )}
      </div>
      <div className="flex justify-end">
        <Button type="submit" disabled={!dirty || busy || !canEdit}>
          {busy ? "Saving…" : "Save changes"}
        </Button>
      </div>
    </form>
  );
}
