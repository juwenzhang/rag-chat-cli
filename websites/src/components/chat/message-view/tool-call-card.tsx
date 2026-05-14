"use client";

import { ChevronDown, Wrench } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import type { UIMessage } from "../types";
import { cn } from "@/lib/utils";

/** A single collapsible tool call — name + status header, args/output body. */
export function ToolCallCard({
  call,
  result,
  status,
}: {
  call: NonNullable<UIMessage["toolCalls"]>[number];
  result?: NonNullable<UIMessage["toolResults"]>[number];
  status: "running" | "done" | "failed";
}) {
  const [open, setOpen] = useState(false);
  const variant =
    status === "failed"
      ? "destructive"
      : status === "done"
        ? "success"
        : "secondary";

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs transition-colors hover:bg-accent"
      >
        <Wrench className="size-3.5 text-muted-foreground" />
        <span className="font-mono font-medium">{call.name}</span>
        <Badge variant={variant} className="text-[10px]">
          {status === "running" && (
            <span className="size-1.5 animate-pulse rounded-full bg-current" />
          )}
          {status}
        </Badge>
        <ChevronDown
          className={cn(
            "ml-auto size-3.5 text-muted-foreground transition-transform",
            open && "rotate-180"
          )}
        />
      </button>
      {open && (
        <div className="space-y-2 border-t border-border bg-muted/30 px-3 py-2.5">
          <div>
            <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Arguments
            </div>
            <pre className="overflow-x-auto rounded bg-background/70 p-2 font-mono text-[11px]">
              {JSON.stringify(call.arguments, null, 2)}
            </pre>
          </div>
          {result && (
            <div>
              <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                {result.error ? "Error" : "Output"}
              </div>
              <pre
                className={cn(
                  "overflow-x-auto rounded p-2 font-mono text-[11px]",
                  result.error
                    ? "border border-destructive/30 bg-destructive/10 text-destructive"
                    : "bg-background/70"
                )}
              >
                {result.error || result.output}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
