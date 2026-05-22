"use client";

import { Badge } from "@/components/ui/badge";

interface Props {
  title: string;
  streaming: boolean;
  thinkingLabel: string;
}

export function ChatToolbar({ title, streaming, thinkingLabel }: Props) {
  return (
    <header className="flex h-12 items-center gap-2 border-b border-border bg-background/80 px-3 pl-14 backdrop-blur sm:h-14 sm:gap-3 sm:px-4 md:pl-4">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <h2 className="truncate text-sm font-medium">{title}</h2>
        {streaming && (
          <Badge variant="secondary" className="gap-1.5 text-primary">
            <span className="size-1.5 animate-pulse rounded-full bg-primary" />
            {thinkingLabel}
          </Badge>
        )}
      </div>
    </header>
  );
}
