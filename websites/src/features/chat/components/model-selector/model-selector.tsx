"use client";

import { ChevronDown, Cpu, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  getButtonLabel,
  getSwitchMessage,
} from "@/features/chat/utils/model-selector-text";
import { api } from "@/lib/api/browser";
import type { ProviderOut, UserPreferenceOut } from "@/lib/api/shared/types";
import { cn } from "@/lib/utils";

import { ModelSelectorMenu, type ProviderWithModels } from "./model-selector-menu";

interface Props {
  sessionId: string;
  /** Per-session provider pin (`null` = inherit user default). */
  initialProviderId: string | null;
  /** Per-session model pin (`null` = inherit user default). */
  initialModel: string | null;
  initialProviders: ProviderOut[];
  initialPreferences: UserPreferenceOut;
  disabled?: boolean;
  /** Called after a successful PATCH so the parent can refresh state. */
  onChange?: (next: { provider_id: string | null; model: string | null }) => void;
}

export function ModelSelector({
  sessionId,
  initialProviderId,
  initialModel,
  initialProviders,
  initialPreferences,
  disabled,
  onChange,
}: Props) {
  const [open, setOpen] = useState(false);
  const [providerId, setProviderId] = useState<string | null>(initialProviderId);
  const [model, setModel] = useState<string | null>(initialModel);
  const [providers, setProviders] = useState<ProviderWithModels[]>(() =>
    initialProviders.map((provider) => ({ ...provider }))
  );
  const [pref] = useState<UserPreferenceOut>(initialPreferences);
  const [saving, setSaving] = useState(false);

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
          <span className="max-w-27.5 truncate sm:max-w-40">{buttonLabel}</span>
          {saving ? (
            <Loader2 className="size-3 animate-spin" />
          ) : (
            <ChevronDown className="size-3 opacity-60" />
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="max-h-[60vh] w-[calc(100vw-2rem)] max-w-72 overflow-y-auto"
      >
        <ModelSelectorMenu
          bootstrapLoading={false}
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
