"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api/browser";
import type { ModelListItem, ProviderOut } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/**
 * Embedding-model dropdown — lists only models with `kind === "embedding"`
 * across the user's enabled providers, one round-trip per provider.
 */
export function EmbeddingModelSelect({
  providers,
  value,
  onChange,
}: {
  providers: ProviderOut[];
  value: string;
  onChange: (next: string) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [grouped, setGrouped] = useState<
    Array<{ providerName: string; models: ModelListItem[] }>
  >([]);

  useEffect(() => {
    const enabled = providers.filter((p) => p.enabled);
    if (enabled.length === 0) {
      setGrouped([]);
      return;
    }
    setLoading(true);
    void (async () => {
      try {
        const results = await Promise.all(
          enabled.map(async (p) => {
            const items = await api.providers
              .listModels(p.id)
              .catch(() => [] as ModelListItem[]);
            return {
              providerName: p.name,
              models: items.filter((m) => m.kind === "embedding"),
            };
          })
        );
        setGrouped(results.filter((g) => g.models.length > 0));
      } finally {
        setLoading(false);
      }
    })();
  }, [providers]);

  const totalCount = grouped.reduce((sum, g) => sum + g.models.length, 0);
  // Show free-text fallback when the typed value isn't in the discovered list
  // (e.g. user pasted a tag the provider hasn't pulled yet).
  const valueInList = grouped.some((g) =>
    g.models.some((m) => m.id === value)
  );

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "flex h-10 w-full rounded-lg border border-input bg-background px-3 text-sm",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      )}
    >
      <option value="">
        {loading
          ? "— Loading… —"
          : totalCount === 0
            ? "— No embedding models found — pull one first —"
            : "— None (fall back to env) —"}
      </option>
      {value && !valueInList && (
        <option value={value}>{value} (not installed)</option>
      )}
      {grouped.map((g) => (
        <optgroup key={g.providerName} label={g.providerName}>
          {g.models.map((m) => (
            <option key={`${g.providerName}::${m.id}`} value={m.id}>
              {m.id}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
