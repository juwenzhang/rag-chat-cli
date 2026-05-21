"use client";

import { ChevronDown, Cpu, Loader2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api/browser";
import type { UserPreferenceOut } from "@/lib/api/shared/types";
import { cn } from "@/lib/utils";

import {
  ModelSelectorMenu,
  type ProviderWithModels,
} from "./model-selector-menu";

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
      setProviders(provData.map((provider) => ({ ...provider })));
      setPref(prefData);
    } catch (err) {
      setProviders([]);
      toast.error(`Failed to load providers: ${(err as Error).message}`);
    } finally {
      setBootstrapLoading(false);
      loadedOnceRef.current = true;
    }
  }, []);

  useEffect(() => {
    if (!loadedOnceRef.current) void loadProviders();
  }, [loadProviders]);

  const fetchModels = useCallback(async (pid: string) => {
    setProviders((prev) =>
      prev.map((provider) =>
        provider.id === pid ? { ...provider, modelsLoading: true } : provider
      )
    );
    try {
      const data = await api.providers.listModels(pid);
      setProviders((prev) =>
        prev.map((provider) =>
          provider.id === pid
            ? { ...provider, models: data, modelsLoading: false, modelsError: undefined }
            : provider
        )
      );
    } catch (err) {
      setProviders((prev) =>
        prev.map((provider) =>
          provider.id === pid
            ? { ...provider, modelsLoading: false, modelsError: (err as Error).message }
            : provider
        )
      );
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    for (const provider of providers) {
      if (
        provider.enabled &&
        !provider.models &&
        !provider.modelsLoading &&
        !provider.modelsError
      ) {
        void fetchModels(provider.id);
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
        toast.success(getSwitchMessage(nextProviderId, nextModel, providers));
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
    providers.find((provider) => provider.id === effectiveProviderId) ?? null;
  const buttonLabel = getButtonLabel(effectiveModel, currentProvider?.name ?? null);

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
        <ModelSelectorMenu
          bootstrapLoading={bootstrapLoading}
          providers={providers}
          pref={pref}
          providerId={providerId}
          model={model}
          onUseDefault={() => {
            void applyPin(null, null);
            setOpen(false);
          }}
          onSelectModel={(nextProviderId, nextModel) => {
            void applyPin(nextProviderId, nextModel);
            setOpen(false);
          }}
          onRefreshProvider={(provider) => void fetchModels(provider)}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function getSwitchMessage(
  nextProviderId: string | null,
  nextModel: string | null,
  providers: ProviderWithModels[]
): string {
  if (nextProviderId === null && nextModel === null) {
    return "Reverted to user default";
  }
  const providerName =
    providers.find((provider) => provider.id === nextProviderId)?.name ?? "provider";
  return nextModel
    ? `Switched to ${providerName} · ${nextModel}`
    : `Switched to ${providerName}`;
}

function getButtonLabel(
  model: string | null,
  providerName: string | null
): string {
  if (model && providerName) return `${providerName} · ${model}`;
  if (model) return model;
  if (providerName) return `${providerName} · auto`;
  return "Default model";
}
