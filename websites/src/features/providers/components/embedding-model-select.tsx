"use client";

import { useEffect, useState } from "react";

import type { ModelListItem, ProviderOut } from "@/lib/api/shared/types";
import { cn } from "@/lib/utils";

/**
 * Embedding-model dropdown — lists only models with `kind === "embedding"`
 * across the user's enabled providers, one round-trip per provider.
 */
export function EmbeddingModelSelect({
  providers,
  value,
  onChange,
  onLoadEmbeddingModels,
}: {
  providers: ProviderOut[];
  value: string;
  onChange: (next: string) => void;
  onLoadEmbeddingModels: (
    providers: ProviderOut[]
  ) => Promise<Array<{ providerName: string; models: ModelListItem[] }>>;
}) {
  const [loading, setLoading] = useState(false);
  const [grouped, setGrouped] = useState<
    Array<{ providerName: string; models: ModelListItem[] }>
  >([]);

  useEffect(() => {
    let cancelled = false;
    const id = window.setTimeout(() => {
      if (providers.filter((p) => p.enabled).length === 0) {
        setGrouped([]);
        return;
      }
      setLoading(true);
      void onLoadEmbeddingModels(providers)
        .then((results) => {
          if (!cancelled) setGrouped(results);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(id);
    };
  }, [onLoadEmbeddingModels, providers]);

  const totalCount = grouped.reduce((sum, g) => sum + g.models.length, 0);
  // Show free-text fallback when the typed value isn't in the discovered list
  // (e.g. user pasted a tag the provider hasn't pulled yet).
  const valueInList = grouped.some((g) => g.models.some((m) => m.id === value));

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
      {value && !valueInList && <option value={value}>{value} (not installed)</option>}
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
