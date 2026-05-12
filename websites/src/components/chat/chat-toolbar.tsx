"use client";

import { Brain } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { ModelSelector } from "./model-selector";

interface Props {
  title: string;
  useRag: boolean;
  onToggleRag: (next: boolean) => void;
  streaming: boolean;
  sessionId: string;
  providerId: string | null;
  model: string | null;
  onModelChange?: (next: { provider_id: string | null; model: string | null }) => void;
}

export function ChatToolbar({
  title,
  useRag,
  onToggleRag,
  streaming,
  sessionId,
  providerId,
  model,
  onModelChange,
}: Props) {
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
      <ModelSelector
        sessionId={sessionId}
        initialProviderId={providerId}
        initialModel={model}
        disabled={streaming}
        onChange={onModelChange}
      />
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant={useRag ? "secondary" : "ghost"}
              size="sm"
              onClick={() => onToggleRag(!useRag)}
              className={cn(useRag && "ring-1 ring-primary/30")}
            >
              <Brain
                className={cn(
                  useRag ? "text-primary" : "text-muted-foreground"
                )}
              />
              <span>RAG</span>
              <Badge
                variant={useRag ? "success" : "outline"}
                className="ml-1 text-[10px]"
              >
                {useRag ? "on" : "off"}
              </Badge>
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {useRag
              ? "Retrieval-augmented context is being added to each turn"
              : "Click to enable retrieval-augmented context"}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <ThemeToggle />
    </header>
  );
}
