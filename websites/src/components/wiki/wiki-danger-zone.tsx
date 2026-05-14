"use client";

import { Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { api } from "@/lib/api/browser";

/** Destructive wiki actions — delete the wiki and all its pages. */
export function WikiDangerZone({
  wikiId,
  wikiName,
  onDeleted,
}: {
  wikiId: string;
  wikiName: string;
  onDeleted: () => void;
}) {
  const [pending, setPending] = useState(false);

  const onConfirm = async () => {
    try {
      await api.wikis.remove(wikiId);
    } catch (err) {
      toast.error((err as Error).message || "Failed to delete");
      throw err;
    }
    toast.success("Wiki deleted");
    onDeleted();
  };

  return (
    <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-5">
      <h2 className="text-base font-semibold text-destructive">Danger zone</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Deleting this wiki also deletes all of its pages. This can&apos;t be
        undone.
      </p>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setPending(true)}
        className="mt-3 border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
      >
        <Trash2 />
        Delete this wiki
      </Button>
      <ConfirmDialog
        open={pending}
        onOpenChange={setPending}
        title={`Delete ${wikiName}?`}
        description="All pages in this wiki will be removed permanently."
        confirmLabel="Delete"
        destructive
        onConfirm={onConfirm}
      />
    </div>
  );
}
