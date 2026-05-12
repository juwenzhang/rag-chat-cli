"use client";

import {
  AlertCircle,
  BookOpen,
  Check,
  ChevronDown,
  Copy,
  RefreshCw,
  Sparkles,
  Wrench,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { Markdown } from "./markdown";
import type { UIMessage } from "./types";

export function MessageView({ message }: { message: UIMessage }) {
  if (message.role === "user") {
    return <UserMessage message={message} />;
  }
  return <AssistantMessage message={message} />;
}

/* ─────────────────────────────────────────────────────────────────
   User message — right-aligned soft-tinted bubble, no avatar
   ───────────────────────────────────────────────────────────────── */
function UserMessage({ message }: { message: UIMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-2xl bg-user-bubble px-4 py-2.5 text-[15px] leading-7 text-user-bubble-foreground shadow-sm">
        <div className="whitespace-pre-wrap break-words">{message.content}</div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
   Assistant message — small logo + full-width markdown + action row
   ───────────────────────────────────────────────────────────────── */
function AssistantMessage({ message }: { message: UIMessage }) {
  return (
    <div className="group flex w-full gap-3">
      <AssistantLogo />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        {message.retrieval && message.retrieval.length > 0 && (
          <RetrievalBlock hits={message.retrieval} />
        )}

        {message.toolCalls && message.toolCalls.length > 0 && (
          <ToolCallsBlock
            calls={message.toolCalls}
            results={message.toolResults || []}
          />
        )}

        {message.content ? (
          <Markdown>{message.content}</Markdown>
        ) : message.streaming ? (
          <ThinkingIndicator />
        ) : null}

        {message.streaming && message.content && (
          <span className="-mt-1 text-xs text-muted-foreground">
            <PulsingDot /> generating…
          </span>
        )}

        {message.error && (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <span>{message.error}</span>
          </div>
        )}

        {!message.streaming && message.content && (
          <ActionRow text={message.content} />
        )}
      </div>
    </div>
  );
}

function AssistantLogo() {
  return (
    <div
      aria-hidden
      className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-lg border border-border bg-card shadow-sm"
    >
      <Sparkles className="size-3.5 text-primary" />
    </div>
  );
}

function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
      <span className="inline-flex gap-1">
        <span className="size-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.3s]" />
        <span className="size-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.15s]" />
        <span className="size-1.5 animate-bounce rounded-full bg-current" />
      </span>
      <span>Thinking</span>
    </div>
  );
}

function PulsingDot() {
  return (
    <span className="mr-1 inline-block size-1.5 animate-pulse rounded-full bg-primary align-middle" />
  );
}

function ActionRow({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      toast.success("Copied");
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Failed to copy");
    }
  };

  return (
    <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={onCopy}
              className="size-7 text-muted-foreground hover:text-foreground"
            >
              {copied ? <Check /> : <Copy />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{copied ? "Copied" : "Copy"}</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              disabled
              className="size-7 text-muted-foreground hover:text-foreground"
              aria-label="Regenerate"
            >
              <RefreshCw />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Regenerate (coming soon)</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────
   Retrieval and tool-call sub-blocks
   ───────────────────────────────────────────────────────────────── */
function RetrievalBlock({
  hits,
}: {
  hits: NonNullable<UIMessage["retrieval"]>;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <BookOpen className="size-3.5" />
        <span>
          Retrieved <strong className="text-foreground">{hits.length}</strong>{" "}
          source{hits.length === 1 ? "" : "s"}
        </span>
        <ChevronDown
          className={cn("size-3.5 transition-transform", open && "rotate-180")}
        />
      </button>
      {open && (
        <ul className="mt-2 flex flex-col gap-2 rounded-lg border border-border bg-card p-3">
          {hits.map((h, i) => (
            <li
              key={`${h.chunk_id}-${i}`}
              className="border-l-2 border-primary/40 pl-3 text-xs"
            >
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px]">
                  [{i + 1}]
                </Badge>
                <span className="truncate font-medium">
                  {h.title || h.document_id.slice(0, 8)}
                </span>
                <span className="ml-auto text-[10px] text-muted-foreground">
                  {h.score.toFixed(3)}
                </span>
              </div>
              <p className="mt-1 line-clamp-3 text-muted-foreground">
                {h.content}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ToolCallsBlock({
  calls,
  results,
}: {
  calls: NonNullable<UIMessage["toolCalls"]>;
  results: NonNullable<UIMessage["toolResults"]>;
}) {
  return (
    <div className="flex flex-col gap-2">
      {calls.map((c) => {
        const result = results.find((r) => r.id === c.id);
        const status = result?.error
          ? "failed"
          : result
            ? "done"
            : "running";
        return <ToolCallCard key={c.id} call={c} result={result} status={status} />;
      })}
    </div>
  );
}

function ToolCallCard({
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
