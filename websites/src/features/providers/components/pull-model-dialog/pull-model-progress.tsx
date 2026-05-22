"use client";

import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ProgressFrame } from "./pull-model-dialog-parts";

export function PullModelProgress({ frame, tag }: { frame: ProgressFrame; tag: string }) {
  const total = frame.total;
  const completed = frame.completed;
  const pct =
    total && completed != null
      ? Math.min(100, Math.max(0, Math.round((completed / total) * 100)))
      : null;

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <div className="flex items-center gap-2 text-sm">
          <Loader2 className="size-4 animate-spin text-primary" />
          <span className="font-mono">{tag}</span>
        </div>
        <p className="text-xs text-muted-foreground">
          {frame.status ?? "Starting…"}
          {frame.digest && (
            <span className="ml-2 font-mono text-[10px] opacity-60">
              {frame.digest.slice(0, 16)}…
            </span>
          )}
        </p>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full bg-primary transition-all",
            pct == null && "w-1/3 animate-pulse"
          )}
          style={pct != null ? { width: `${pct}%` } : undefined}
        />
      </div>
      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <span>
          {completed != null && total != null
            ? `${formatBytes(completed)} / ${formatBytes(total)}`
            : "…"}
        </span>
        {pct != null && <span>{pct}%</span>}
      </div>
    </div>
  );
}

function formatBytes(n: number): string {
  if (n <= 0) return "0";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`;
}
