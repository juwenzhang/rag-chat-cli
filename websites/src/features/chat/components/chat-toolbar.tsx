"use client";

import { Badge } from "@/components/ui/badge";

interface Props {
  title: string;
  streaming: boolean;
}

export function ChatToolbar({ title, streaming }: Props) {
  return (
    <header className="flex h-14 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <h2 className="truncate text-sm font-medium">{title}</h2>
        {streaming && (
          <Badge variant="secondary" className="gap-1.5 text-primary">
            <span className="size-1.5 animate-pulse rounded-full bg-primary" />
            Thinking
          </Badge>
        )}
      </div>
    </header>
  );
}
