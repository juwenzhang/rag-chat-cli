"use client";

import { Loader2, Save } from "lucide-react";
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
import { Textarea } from "@/components/ui/input";
import { api } from "@/lib/api/browser";
import type { ModelListItem } from "@/lib/api/types";

/** Per-(provider, model) free-text note editor — shown on hover in pickers. */
export function EditDescriptionDialog({
  providerId,
  model,
  onOpenChange,
  onSaved,
}: {
  providerId: string;
  model: ModelListItem | null;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setText(model?.description ?? "");
  }, [model]);

  const save = async () => {
    if (!model) return;
    setSaving(true);
    try {
      await api.providers.upsertModelMeta(
        providerId,
        model.id,
        text.trim() || null
      );
      toast.success("Description saved");
      onSaved();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={model !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Edit description</DialogTitle>
          <DialogDescription>
            Free text shown on hover in the model picker. Empty clears it.
          </DialogDescription>
        </DialogHeader>
        {model && (
          <>
            <div className="space-y-1.5">
              <Label htmlFor="model_desc" className="font-mono text-xs">
                {model.id}
              </Label>
              <Textarea
                id="model_desc"
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={4}
                maxLength={2000}
                placeholder="What is this model for?"
                className="resize-none"
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => onOpenChange(false)}
                disabled={saving}
              >
                Cancel
              </Button>
              <Button onClick={save} disabled={saving}>
                {saving ? <Loader2 className="animate-spin" /> : <Save />}
                Save
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
