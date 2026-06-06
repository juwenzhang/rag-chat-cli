"use client";

import { BookOpen, Clock, Cpu, Hash } from "lucide-react";

import { formatDuration, formatTokens } from "@/features/chat/utils/format-numbers";

import type { UIMessage } from "../types";

import { SourcesDrawerTrigger } from "./sources-block";

/** Compact metadata line under a finished answer — model, tokens, duration. */
export function MessageFooter({ message }: { message: UIMessage }) {
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
  if (message.sources && message.sources.length > 0) {
    parts.push(
      <SourcesDrawerTrigger key="sources" sources={message.sources}>
        <button
          type="button"
          className="inline-flex items-center gap-1 transition-colors hover:text-foreground hover:underline"
        >
          <BookOpen className="size-3" />
          {message.sources.length} source{message.sources.length === 1 ? "" : "s"}
        </button>
      </SourcesDrawerTrigger>
    );
  }
  if (parts.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 text-[11px] text-muted-foreground">
      {parts}
    </div>
  );
}
