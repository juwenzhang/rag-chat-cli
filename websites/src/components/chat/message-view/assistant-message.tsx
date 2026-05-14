"use client";

import { Sparkles } from "lucide-react";

import { Markdown } from "../markdown";
import type { UIMessage } from "../types";

import { ActionRow } from "./action-row";
import { MessageErrorBlock } from "./message-error-block";
import { MessageFooter } from "./message-footer";
import { RetrievalBlock } from "./retrieval-block";
import { ToolCallsBlock } from "./tool-calls-block";

/** Assistant message — small logo + full-width markdown + action row. */
export function AssistantMessage({
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

// ── Presentational atoms — private to the assistant message ─────────

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
