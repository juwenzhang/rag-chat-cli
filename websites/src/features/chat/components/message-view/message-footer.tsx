"use client";

import { Clock, Cpu, Hash } from "lucide-react";

import type { UIMessage } from "../types";

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
    (message.usage?.prompt_tokens != null &&
    message.usage?.completion_tokens != null
      ? (message.usage.prompt_tokens ?? 0) +
        (message.usage.completion_tokens ?? 0)
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
