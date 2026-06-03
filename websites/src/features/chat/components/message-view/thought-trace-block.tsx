"use client";

import { Brain, ChevronDown } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";

export function ThoughtTraceBlock({ thoughts }: { thoughts: string[] }) {
  const [open, setOpen] = useState(false);
  if (thoughts.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex w-fit items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <Brain className="size-3.5" />
        <span>
          Thinking trace <strong className="text-foreground">{thoughts.length}</strong>
        </span>
        <ChevronDown
          className={cn("size-3.5 transition-transform", open && "rotate-180")}
        />
      </button>

      {open && (
        <ol className="flex w-full flex-col gap-1.5 rounded-lg border border-border bg-card p-3 text-xs text-muted-foreground">
          {thoughts.map((thought, index) => (
            <li key={`${thought}-${index}`} className="flex gap-2">
              <span className="mt-0.5 text-[10px] text-muted-foreground/70">
                {index + 1}.
              </span>
              <span className="whitespace-pre-wrap wrap-break-word">{thought}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
