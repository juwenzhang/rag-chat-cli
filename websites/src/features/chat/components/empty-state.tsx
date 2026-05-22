"use client";

import { BookOpen, Code2, Lightbulb, Sparkles, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export interface EmptyStateExample {
  icon: LucideIcon;
  title: string;
  prompt: string;
}

export interface EmptyStateCopy {
  title: string;
  titleAccent: string;
  description: string;
  examples: EmptyStateExample[];
}

export const EMPTY_STATE_ICONS = {
  concept: Lightbulb,
  refactor: Code2,
  summary: BookOpen,
  brainstorm: Sparkles,
} as const;

export function EmptyState({
  copy,
  onPick,
}: {
  copy: EmptyStateCopy;
  onPick: (prompt: string) => void;
}) {
  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center px-4 py-8">
      <div
        aria-hidden
        className="mb-5 flex size-16 items-center justify-center rounded-2xl bg-brand-gradient text-white shadow-xl shadow-primary/30"
      >
        <Sparkles className="size-8" />
      </div>
      <h2 className="text-3xl font-semibold tracking-tight">
        {copy.title} <span className="text-brand-gradient">{copy.titleAccent}</span>
      </h2>
      <p className="mt-2 max-w-md text-center text-sm text-muted-foreground">
        {copy.description}
      </p>

      <div className="mt-10 grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
        {copy.examples.map(({ icon: Icon, title, prompt }) => (
          <button
            key={title}
            type="button"
            onClick={() => onPick(prompt)}
            className={cn(
              "group rounded-xl border border-border bg-card p-4 text-left transition-all",
              "hover:-translate-y-0.5 hover:border-primary/40 hover:bg-accent hover:shadow-md hover:shadow-primary/5"
            )}
          >
            <div className="mb-2 flex size-8 items-center justify-center rounded-lg bg-secondary text-foreground transition-colors group-hover:bg-brand-gradient group-hover:text-white">
              <Icon className="size-4" />
            </div>
            <div className="text-sm font-medium">{title}</div>
            <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">
              {prompt}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
