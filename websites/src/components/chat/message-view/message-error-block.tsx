"use client";

import { AlertCircle, ExternalLink } from "lucide-react";

/**
 * Recognises upstream-provider conditions worth their own CTA — currently
 * just Ollama Cloud subscription paywalls. The detection is text-based on
 * the LLMError message (e.g. ``"this model requires a subscription, upgrade
 * for access: https://ollama.com/upgrade ..."``) because the backend hands
 * us the message verbatim without a structured code today.
 */
export function MessageErrorBlock({ error }: { error: string }) {
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
