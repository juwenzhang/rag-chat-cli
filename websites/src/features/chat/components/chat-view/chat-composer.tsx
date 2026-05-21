"use client";

import { Brain, Send, Square } from "lucide-react";
import type { FormEvent, KeyboardEvent, RefObject } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { SessionMeta } from "@/lib/api/shared/types";
import { cn } from "@/lib/utils";

import { ModelSelector } from "../model-selector";

export function ChatComposer({
  sessionId,
  sessionMeta,
  input,
  streaming,
  useRag,
  providerId,
  model,
  inputRef,
  onInputChange,
  onSubmit,
  onKeyDown,
  onToggleRag,
  onModelChange,
  onAbort,
}: {
  sessionId: string;
  sessionMeta?: SessionMeta | null;
  input: string;
  streaming: boolean;
  useRag: boolean;
  providerId: string | null;
  model: string | null;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  onInputChange: (next: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onToggleRag: () => void;
  onModelChange: (next: { provider_id: string | null; model: string | null }) => void;
  onAbort: () => void;
}) {
  return (
    <form
      onSubmit={onSubmit}
      className="border-t border-border bg-background/80 px-4 py-4 backdrop-blur"
    >
      <div className="mx-auto max-w-3xl">
        <div
          className={cn(
            "relative flex flex-col gap-1 rounded-2xl border border-border bg-card p-2 shadow-sm transition-all",
            "focus-within:border-primary/50 focus-within:shadow-md focus-within:shadow-primary/5"
          )}
        >
          <Textarea
            ref={inputRef}
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask anything…  (Enter to send, Shift+Enter for newline)"
            rows={1}
            className={cn(
              "min-h-[44px] resize-none border-0 bg-transparent px-2 py-2.5 shadow-none focus-visible:ring-0",
              "max-h-[200px]"
            )}
            style={{ height: "auto" }}
            onInput={(event) => {
              const el = event.currentTarget;
              el.style.height = "auto";
              el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
            }}
            disabled={streaming}
          />
          <ComposerActions
            sessionId={sessionId}
            sessionMeta={sessionMeta}
            input={input}
            streaming={streaming}
            useRag={useRag}
            providerId={providerId}
            model={model}
            onToggleRag={onToggleRag}
            onModelChange={onModelChange}
            onAbort={onAbort}
          />
        </div>
        <p className="mt-2 text-center text-[11px] text-muted-foreground">
          lhx-rag may produce inaccurate information. Responses are not stored
          unless you save them to your knowledge base.
        </p>
      </div>
    </form>
  );
}

function ComposerActions({
  sessionId,
  sessionMeta,
  input,
  streaming,
  useRag,
  providerId,
  model,
  onToggleRag,
  onModelChange,
  onAbort,
}: {
  sessionId: string;
  sessionMeta?: SessionMeta | null;
  input: string;
  streaming: boolean;
  useRag: boolean;
  providerId: string | null;
  model: string | null;
  onToggleRag: () => void;
  onModelChange: (next: { provider_id: string | null; model: string | null }) => void;
  onAbort: () => void;
}) {
  return (
    <div className="flex items-center gap-1 border-t border-border/60 pt-1.5">
      <RagToggle enabled={useRag} disabled={streaming} onToggle={onToggleRag} />
      <div className="ml-auto flex items-center gap-1">
        <ModelSelector
          sessionId={sessionId}
          initialProviderId={providerId ?? sessionMeta?.provider_id ?? null}
          initialModel={model ?? sessionMeta?.model ?? null}
          disabled={streaming}
          onChange={onModelChange}
        />
        {streaming ? (
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={onAbort}
            className="size-9 shrink-0 rounded-xl"
            aria-label="Stop"
          >
            <Square className="size-4 fill-current" />
          </Button>
        ) : (
          <Button
            type="submit"
            size="icon"
            disabled={!input.trim()}
            className="size-9 shrink-0 rounded-xl"
            aria-label="Send"
          >
            <Send className="size-4" />
          </Button>
        )}
      </div>
    </div>
  );
}

function RagToggle({
  enabled,
  disabled,
  onToggle,
}: {
  enabled: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onToggle}
            disabled={disabled}
            className={cn(
              "gap-1.5 text-xs font-normal",
              enabled ? "text-foreground" : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Brain
              className={cn(
                "size-3.5",
                enabled ? "text-primary" : "text-muted-foreground"
              )}
            />
            <span>RAG</span>
            <Badge
              variant={enabled ? "success" : "outline"}
              className="ml-0.5 text-[9px]"
            >
              {enabled ? "on" : "off"}
            </Badge>
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          {enabled
            ? "Retrieval-augmented context is being added to each turn"
            : "Click to enable retrieval-augmented context"}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
