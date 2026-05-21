"use client";

import {
  BookOpen,
  Code2,
  Lightbulb,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

interface Example {
  icon: LucideIcon;
  title: string;
  prompt: string;
}

const EXAMPLES: Example[] = [
  {
    icon: Lightbulb,
    title: "Explain a concept",
    prompt: "Explain how retrieval-augmented generation (RAG) works in plain English.",
  },
  {
    icon: Code2,
    title: "Refactor code",
    prompt:
      "Refactor this Python snippet to use type hints and remove the global variable.",
  },
  {
    icon: BookOpen,
    title: "Summarise a document",
    prompt:
      "Summarise the key takeaways from my recent notes about vector search performance.",
  },
  {
    icon: Sparkles,
    title: "Brainstorm",
    prompt:
      "Give me five creative blog post ideas about local-first AI applications.",
  },
];

export function EmptyState({
  onPick,
}: {
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
        How can I <span className="text-brand-gradient">help</span> you today?
      </h2>
      <p className="mt-2 max-w-md text-center text-sm text-muted-foreground">
        Ask anything — I&apos;ll reason step by step, call tools, and retrieve
        from your knowledge base.
      </p>

      <div className="mt-10 grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
        {EXAMPLES.map(({ icon: Icon, title, prompt }) => (
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
