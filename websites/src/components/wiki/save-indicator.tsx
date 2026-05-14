"use client";

import { Check, Loader2 } from "lucide-react";

import { formatRelative } from "@/lib/utils";

/** Autosave lifecycle states for a wiki page edit session. */
export type WikiSaveStatus =
  | "idle"
  | "dirty"
  | "saving"
  | "saved"
  | "conflict";

/** Compact autosave status pill shown in the wiki editor header. */
export function SaveIndicator({
  status,
  lastSavedAt,
}: {
  status: WikiSaveStatus;
  lastSavedAt: Date | null;
}) {
  if (status === "saving") {
    return (
      <span className="inline-flex items-center gap-1">
        <Loader2 className="size-3 animate-spin" />
        Saving…
      </span>
    );
  }
  if (status === "conflict") {
    return (
      <span className="inline-flex items-center gap-1 text-destructive">
        Conflict — reloaded
      </span>
    );
  }
  if (status === "dirty") {
    return <span className="text-muted-foreground/70">Unsaved</span>;
  }
  if (status === "saved" && lastSavedAt) {
    return (
      <span className="inline-flex items-center gap-1">
        <Check className="size-3 text-primary" />
        Saved {formatRelative(lastSavedAt.toISOString())}
      </span>
    );
  }
  return null;
}
