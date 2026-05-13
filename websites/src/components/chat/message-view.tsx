"use client";

import {
  AlertCircle,
  Bookmark,
  BookmarkCheck,
  BookOpen,
  ChevronDown,
  Clock,
  Cpu,
  ExternalLink,
  Hash,
  RefreshCw,
  Share2,
  Sparkles,
  Wrench,
  Check,
  Copy
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ShareDialog } from "@/components/share/share-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { ShareOut } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { Markdown } from "./markdown";
import type { UIMessage } from "./types";

interface MessageViewProps {
  message: UIMessage;
  /**
   * Server id of the user message that precedes this turn. Required for
   * Share / Bookmark actions on an assistant message — both endpoints key
   * on the (user_message_id, assistant_message_id) pair.
   */
  prevUserMessageId?: string;
  /**
   * Set on the most recent assistant message when it's safe to
   * regenerate (stream finished, message persisted, no other stream
   * in flight). Triggers the chat view's regenerate pipeline.
   */
  onRegenerate?: () => void;
}

export function MessageView({
  message,
  prevUserMessageId,
  onRegenerate,
}: MessageViewProps) {
  if (message.role === "user") {
    return <UserMessage message={message} />;
  }
  return (
    <AssistantMessage
      message={message}
      prevUserMessageId={prevUserMessageId}
      onRegenerate={onRegenerate}
    />
  );
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
function AssistantMessage({
  message,
  prevUserMessageId,
  onRegenerate,
}: {
  message: UIMessage;
  prevUserMessageId?: string;
  onRegenerate?: () => void;
}) {
  // Share / Bookmark need both server IDs. Optimistic rows during the
  // active stream lack them (and the preceding user row is also still local).
  const canPersistAction =
    !!message.persisted && !!prevUserMessageId && !!message.id;

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

        {message.error && <MessageErrorBlock error={message.error} />}

        {!message.streaming && message.content && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <ActionRow
              text={message.content}
              messageId={canPersistAction ? message.id : undefined}
              userMessageId={canPersistAction ? prevUserMessageId : undefined}
              onRegenerate={onRegenerate}
            />
            <MessageFooter message={message} />
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Recognises upstream-provider conditions worth their own CTA — currently
 * just Ollama Cloud subscription paywalls. The detection is text-based on
 * the LLMError message (e.g. ``"this model requires a subscription, upgrade
 * for access: https://ollama.com/upgrade ..."``) because the backend hands
 * us the message verbatim without a structured code today.
 */
function MessageErrorBlock({ error }: { error: string }) {
  const subscriptionUrl = extractSubscriptionUpgradeUrl(error);
  if (subscriptionUrl) {
    return (
      <div className="space-y-2 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2.5 text-sm">
        <div className="flex items-start gap-2 text-foreground">
          <AlertCircle className="mt-0.5 size-4 shrink-0 text-warning" />
          <span>
            This model requires a paid Ollama subscription. Open the upgrade
            page to enable cloud access, then try again.
          </span>
        </div>
        <a
          href={subscriptionUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-md border border-warning/40 bg-warning/15 px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-warning/25"
        >
          Open Ollama upgrade
          <ExternalLink className="size-3" />
        </a>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      <span className="whitespace-pre-wrap break-words">{error}</span>
    </div>
  );
}

function extractSubscriptionUpgradeUrl(msg: string): string | null {
  // Match a URL on https://ollama.com/upgrade* — the error text often has
  // additional trailing context like "(ref: <uuid>)" which we must not capture.
  const m = msg.match(/https?:\/\/ollama\.com\/upgrade[^\s")]*/i);
  if (m) return m[0];
  if (/requires a subscription/i.test(msg)) return "https://ollama.com/upgrade";
  return null;
}

function MessageFooter({ message }: { message: UIMessage }) {
  const parts: React.ReactNode[] = [];
  if (message.model || message.provider) {
    parts.push(
      <span key="model" className="inline-flex items-center gap-1">
        <Cpu className="size-3" />
        {message.provider && message.model
          ? `${message.provider} · ${message.model}`
          : message.model || message.provider}
      </span>
    );
  }
  const totalTokens =
    message.usage?.total_tokens ??
    (message.usage?.prompt_tokens != null && message.usage?.completion_tokens != null
      ? (message.usage.prompt_tokens ?? 0) + (message.usage.completion_tokens ?? 0)
      : undefined);
  if (totalTokens != null) {
    parts.push(
      <span key="tokens" className="inline-flex items-center gap-1">
        <Hash className="size-3" />
        {formatTokens(totalTokens)} tok
      </span>
    );
  }
  if (message.durationMs != null) {
    parts.push(
      <span key="duration" className="inline-flex items-center gap-1">
        <Clock className="size-3" />
        {formatDuration(message.durationMs)}
      </span>
    );
  }
  if (parts.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 text-[11px] text-muted-foreground">
      {parts}
    </div>
  );
}

function formatTokens(n: number): string {
  if (n < 1000) return String(n);
  return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)}s`;
  const m = Math.floor(s / 60);
  const r = Math.round(s - m * 60);
  return `${m}m${r}s`;
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

function ActionRow({
  text,
  messageId,
  userMessageId,
  onRegenerate,
}: {
  text: string;
  /** Server id of the assistant message — present once persisted. */
  messageId?: string;
  /** Server id of the preceding user message — paired with ``messageId``. */
  userMessageId?: string;
  /** Set by ChatView on the trailing assistant turn when re-streaming
   *  is allowed (no in-flight stream, message persisted). */
  onRegenerate?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [share, setShare] = useState<ShareOut | null>(null);
  const [sharing, setSharing] = useState(false);
  const [bookmarked, setBookmarked] = useState(false);
  const [bookmarking, setBookmarking] = useState(false);

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

  const onShare = async () => {
    if (!messageId || !userMessageId) return;
    setSharing(true);
    try {
      const res = await fetch("/api/shares", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_message_id: userMessageId,
          assistant_message_id: messageId,
        }),
      });
      if (!res.ok) {
        toast.error("Failed to create share link");
        return;
      }
      const data = (await res.json()) as ShareOut;
      setShare(data);
      setShareOpen(true);
    } finally {
      setSharing(false);
    }
  };

  const onBookmark = async () => {
    if (!messageId || !userMessageId) return;
    setBookmarking(true);
    try {
      const res = await fetch("/api/bookmarks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_message_id: userMessageId,
          assistant_message_id: messageId,
        }),
      });
      if (!res.ok) {
        toast.error("Failed to bookmark");
        return;
      }
      setBookmarked(true);
      toast.success("Saved to bookmarks");
    } finally {
      setBookmarking(false);
    }
  };

  const canPersist = !!messageId && !!userMessageId;

  return (
    <>
      <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={onCopy}
                className="size-7 text-muted-foreground hover:text-foreground"
                aria-label="Copy"
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
                onClick={onShare}
                disabled={!canPersist || sharing}
                className="size-7 text-muted-foreground hover:text-foreground"
                aria-label="Share"
              >
                <Share2 />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {canPersist ? "Share this Q&A" : "Available after refresh"}
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={onBookmark}
                disabled={!canPersist || bookmarking || bookmarked}
                className={cn(
                  "size-7 text-muted-foreground hover:text-foreground",
                  bookmarked && "text-primary"
                )}
                aria-label="Bookmark"
              >
                {bookmarked ? <BookmarkCheck /> : <Bookmark />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {bookmarked
                ? "Saved"
                : canPersist
                  ? "Save to bookmarks"
                  : "Available after refresh"}
            </TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                disabled={!onRegenerate}
                onClick={onRegenerate}
                className="size-7 text-muted-foreground hover:text-foreground"
                aria-label="Regenerate"
              >
                <RefreshCw />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {onRegenerate ? "Regenerate this answer" : "Regenerate"}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <ShareDialog
        open={shareOpen}
        onOpenChange={setShareOpen}
        share={share}
        onRevoked={() => {
          setShare(null);
          setShareOpen(false);
        }}
      />
    </>
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
