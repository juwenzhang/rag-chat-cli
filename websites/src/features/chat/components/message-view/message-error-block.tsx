"use client";

import { AlertCircle, ExternalLink } from "lucide-react";

import { ErrorCode } from "@/lib/api/shared/enums";
import type { ErrorPayload } from "@/lib/api/shared/types";

/**
 * Renders the structured ``error`` event payload. Branches on
 * ``error.code`` (no text matching). Code dictionary lives in
 * ``docs/backend/ERROR_CODES.md``.
 */
export function MessageErrorBlock({ error }: { error: ErrorPayload }) {
  const variant = pickVariant(error);
  if (variant.kind === "subscription") {
    return (
      <CalloutBlock
        tone="warning"
        text="This model requires a paid Ollama subscription. Open the upgrade page to enable cloud access, then try again."
        cta={{ href: variant.href, label: "Open Ollama upgrade" }}
      />
    );
  }
  if (variant.kind === "rateLimited") {
    const suffix = error.retry_after ? ` Retry in ~${error.retry_after}s.` : "";
    return (
      <CalloutBlock
        tone="warning"
        text={`Upstream is rate-limiting requests right now.${suffix}`}
      />
    );
  }
  if (variant.kind === "unauthorized") {
    return (
      <CalloutBlock
        tone="warning"
        text="Provider rejected the API key. Open Settings → Providers and reconfigure it."
      />
    );
  }
  if (variant.kind === "modelNotFound") {
    return (
      <CalloutBlock
        tone="warning"
        text="The selected model is not available on the upstream. Pull it locally or switch model."
      />
    );
  }
  return (
    <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      <span className="whitespace-pre-wrap break-words">
        {error.message || error.code}
      </span>
    </div>
  );
}

type Variant =
  | { kind: "subscription"; href: string }
  | { kind: "rateLimited" }
  | { kind: "unauthorized" }
  | { kind: "modelNotFound" }
  | { kind: "generic" };

function pickVariant(error: ErrorPayload): Variant {
  switch (error.code) {
    case ErrorCode.LlmSubscriptionRequired:
      return {
        kind: "subscription",
        href: error.upstream_url ?? "https://ollama.com/upgrade",
      };
    case ErrorCode.LlmRateLimited:
      return { kind: "rateLimited" };
    case ErrorCode.LlmUnauthorized:
      return { kind: "unauthorized" };
    case ErrorCode.LlmModelNotFound:
      return { kind: "modelNotFound" };
    default:
      return { kind: "generic" };
  }
}

function CalloutBlock({
  tone,
  text,
  cta,
}: {
  tone: "warning";
  text: string;
  cta?: { href: string; label: string };
}) {
  const palette =
    tone === "warning"
      ? "border-warning/40 bg-warning/10 text-foreground"
      : "border-destructive/30 bg-destructive/10 text-destructive";
  return (
    <div className={`space-y-2 rounded-lg border px-3 py-2.5 text-sm ${palette}`}>
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 size-4 shrink-0 text-warning" />
        <span>{text}</span>
      </div>
      {cta && (
        <a
          href={cta.href}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-md border border-warning/40 bg-warning/15 px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-warning/25"
        >
          {cta.label}
          <ExternalLink className="size-3" />
        </a>
      )}
    </div>
  );
}
