"use client";

import {
  ChevronDown,
  Cog,
  Cpu,
  Loader2,
  RefreshCcw,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api/browser";
import type {
  ModelListItem,
  ProviderOut,
  UserPreferenceOut,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface Props {
  sessionId: string;
  /** Per-session provider pin (`null` = inherit user default). */
  initialProviderId: string | null;
  /** Per-session model pin (`null` = inherit user default). */
  initialModel: string | null;
  disabled?: boolean;
  /** Called after a successful PATCH so the parent can refresh state. */
  onChange?: (next: { provider_id: string | null; model: string | null }) => void;
}

interface ProviderWithModels extends ProviderOut {
  models?: ModelListItem[];
  modelsError?: string;
  modelsLoading?: boolean;
}

export function ModelSelector({
  sessionId,
  initialProviderId,
  initialModel,
  disabled,
  onChange,
}: Props) {
  const [open, setOpen] = useState(false);
  const [providerId, setProviderId] = useState<string | null>(initialProviderId);
  const [model, setModel] = useState<string | null>(initialModel);
  const [providers, setProviders] = useState<ProviderWithModels[]>([]);
  const [pref, setPref] = useState<UserPreferenceOut | null>(null);
  const [bootstrapLoading, setBootstrapLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const loadedOnceRef = useRef(false);

  const loadProviders = useCallback(async () => {
    setBootstrapLoading(true);
    try {
      const [provData, prefData] = await Promise.all([
        api.providers.list(),
        api.me.getPreferences(),
      ]);
      setProviders(provData.map((p) => ({ ...p })));
      setPref(prefData);
    } catch (err) {
      setProviders([]);
      toast.error(`Failed to load providers: ${(err as Error).message}`);
    } finally {
      setBootstrapLoading(false);
      loadedOnceRef.current = true;
    }
  }, []);

  // Eagerly load providers + preferences on mount so the trigger button can
  // display the effective provider/model name (instead of always saying
  // "Default model" until the dropdown is opened). Also triggers the
  // first-time backend onboarding seed.
  useEffect(() => {
    if (!loadedOnceRef.current) void loadProviders();
  }, [loadProviders]);

  // Lazy-load each provider's model list the first time its section
  // becomes visible. `bff` is always `no-store`, so the "refresh" button
  // and the lazy first load share one path.
  const fetchModels = useCallback(async (pid: string) => {
    setProviders((prev) =>
      prev.map((p) => (p.id === pid ? { ...p, modelsLoading: true } : p))
    );
    try {
      const data = await api.providers.listModels(pid);
      setProviders((prev) =>
        prev.map((p) =>
          p.id === pid
            ? { ...p, models: data, modelsLoading: false, modelsError: undefined }
            : p
        )
      );
    } catch (err) {
      setProviders((prev) =>
        prev.map((p) =>
          p.id === pid
            ? { ...p, modelsLoading: false, modelsError: (err as Error).message }
            : p
        )
      );
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    for (const p of providers) {
      if (p.enabled && !p.models && !p.modelsLoading && !p.modelsError) {
        void fetchModels(p.id);
      }
    }
  }, [open, providers, fetchModels]);

  const applyPin = useCallback(
    async (nextProviderId: string | null, nextModel: string | null) => {
      setSaving(true);
      try {
        await api.chat.updateSession(sessionId, {
          provider_id: nextProviderId ?? undefined,
          model: nextModel ?? undefined,
          clear_provider_id: nextProviderId === null,
          clear_model: nextModel === null,
        });
        setProviderId(nextProviderId);
        setModel(nextModel);
        onChange?.({ provider_id: nextProviderId, model: nextModel });
        if (nextProviderId === null && nextModel === null) {
          toast.success("Reverted to user default");
        } else {
          const providerName =
            providers.find((p) => p.id === nextProviderId)?.name ?? "provider";
          toast.success(
            nextModel
              ? `Switched to ${providerName} · ${nextModel}`
              : `Switched to ${providerName}`
          );
        }
      } catch (err) {
        toast.error(`Failed to switch model: ${(err as Error).message}`);
      } finally {
        setSaving(false);
      }
    },
    [sessionId, onChange, providers]
  );

  const effectiveProviderId = providerId ?? pref?.default_provider_id ?? null;
  const effectiveModel = model ?? pref?.default_model ?? null;
  const currentProvider =
    providers.find((p) => p.id === effectiveProviderId) ?? null;

  const buttonLabel = (() => {
    if (effectiveModel && currentProvider)
      return `${currentProvider.name} · ${effectiveModel}`;
    if (effectiveModel) return effectiveModel;
    if (currentProvider) return `${currentProvider.name} · auto`;
    return "Default model";
  })();

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          disabled={disabled}
          className={cn(
            "gap-1.5 text-xs font-normal text-muted-foreground hover:text-foreground",
            providerId || model ? "text-foreground" : ""
          )}
        >
          <Cpu className="size-3.5" />
          <span className="max-w-[160px] truncate">{buttonLabel}</span>
          {saving ? (
            <Loader2 className="size-3 animate-spin" />
          ) : (
            <ChevronDown className="size-3 opacity-60" />
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72 max-h-[60vh] overflow-y-auto">
        {bootstrapLoading ? (
          <div className="flex items-center gap-2 px-2 py-3 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            Loading providers…
          </div>
        ) : providers.length === 0 ? (
          <EmptyProvidersHint />
        ) : (
          <>
            <DropdownMenuItem
              onSelect={(e) => {
                e.preventDefault();
                void applyPin(null, null);
                setOpen(false);
              }}
              className="gap-2"
            >
              <Sparkles className="text-primary" />
              <div className="flex flex-col">
                <span>Use user default</span>
                <span className="text-[11px] text-muted-foreground">
                  {pref?.default_provider_id
                    ? `${
                        providers.find((p) => p.id === pref.default_provider_id)
                          ?.name ?? "—"
                      }${
                        pref.default_model ? ` · ${pref.default_model}` : ""
                      }`
                    : "No default set — falls back to env config"}
                </span>
              </div>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            {providers.map((p) => (
              <div key={p.id} className="px-1 py-1">
                <div className="flex items-center justify-between px-1 py-1">
                  <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                    <span>{p.name}</span>
                    <span className="rounded bg-muted px-1 py-0.5 text-[9px] uppercase tracking-wide">
                      {p.type}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      void fetchModels(p.id);
                    }}
                    aria-label="Refresh models"
                    className="rounded p-0.5 text-muted-foreground/70 hover:bg-foreground/5 hover:text-foreground"
                  >
                    <RefreshCcw
                      className={cn(
                        "size-3",
                        p.modelsLoading && "animate-spin"
                      )}
                    />
                  </button>
                </div>
                {p.modelsError ? (
                  <div className="px-2 py-1.5 text-[11px] text-destructive">
                    {p.modelsError}
                  </div>
                ) : p.modelsLoading && !p.models ? (
                  <div className="flex items-center gap-2 px-2 py-1.5 text-[11px] text-muted-foreground">
                    <Loader2 className="size-3 animate-spin" />
                    Loading models…
                  </div>
                ) : p.models && p.models.length > 0 ? (
                  (() => {
                    const chatModels = p.models.filter(
                      (m) => m.kind !== "embedding"
                    );
                    const embedCount = p.models.length - chatModels.length;
                    return (
                      <>
                        {chatModels.length === 0 ? (
                          <div className="px-2 py-1.5 text-[11px] text-muted-foreground">
                            No chat models — only embedding models are
                            installed.
                          </div>
                        ) : (
                          chatModels.map((m) => {
                            const active =
                              providerId === p.id && model === m.id;
                            return (
                              <DropdownMenuItem
                                key={m.id}
                                onSelect={(e) => {
                                  e.preventDefault();
                                  void applyPin(p.id, m.id);
                                  setOpen(false);
                                }}
                                title={m.description ?? undefined}
                                className={cn(
                                  "flex-col items-start gap-0.5 pl-3 text-[12.5px]",
                                  active && "bg-accent/60"
                                )}
                              >
                                <div className="flex w-full items-center gap-2">
                                  <Cpu
                                    className={cn(
                                      "size-3.5",
                                      active
                                        ? "text-primary"
                                        : "text-muted-foreground"
                                    )}
                                  />
                                  <span className="truncate">{m.id}</span>
                                  {m.size != null && (
                                    <span className="ml-auto text-[10px] text-muted-foreground">
                                      {formatSize(m.size)}
                                    </span>
                                  )}
                                </div>
                                {m.description && (
                                  <span className="line-clamp-2 pl-5 text-[10.5px] font-normal text-muted-foreground">
                                    {m.description}
                                  </span>
                                )}
                              </DropdownMenuItem>
                            );
                          })
                        )}
                        {embedCount > 0 && (
                          <div className="px-3 py-1 text-[10px] text-muted-foreground/80">
                            +{embedCount} embedding model
                            {embedCount === 1 ? "" : "s"} hidden — set under{" "}
                            <Link
                              href="/settings/providers"
                              className="underline hover:text-foreground"
                            >
                              Settings
                            </Link>
                          </div>
                        )}
                      </>
                    );
                  })()
                ) : (
                  <div className="px-2 py-1.5 text-[11px] text-muted-foreground">
                    No models exposed.
                  </div>
                )}
              </div>
            ))}
            <DropdownMenuSeparator />
          </>
        )}
        <DropdownMenuLabel className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-widest">Providers</span>
        </DropdownMenuLabel>
        <DropdownMenuItem asChild>
          <Link href="/settings/providers" className="gap-2">
            <Cog />
            Manage providers
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function formatSize(bytes: number): string {
  if (bytes <= 0) return "";
  const units = ["B", "K", "M", "G", "T"];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(n < 10 ? 1 : 0)}${units[i]}`;
}

function EmptyProvidersHint() {
  return (
    <div className="px-3 py-3 text-xs">
      <p className="text-muted-foreground">
        No LLM providers configured yet.
      </p>
      <Link
        href="/settings/providers"
        className="mt-1 inline-block font-medium text-primary hover:underline"
      >
        Add your first provider →
      </Link>
    </div>
  );
}
