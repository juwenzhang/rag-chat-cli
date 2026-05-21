"use client";

import { Cog, Loader2, Sparkles } from "lucide-react";
import Link from "next/link";

import {
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import type {
  ModelListItem,
  ProviderOut,
  UserPreferenceOut,
} from "@/lib/api/shared/types";

import { ProviderModelGroup } from "./model-selector-provider-group";

export interface ProviderWithModels extends ProviderOut {
  models?: ModelListItem[];
  modelsError?: string;
  modelsLoading?: boolean;
}

export function ModelSelectorMenu({
  bootstrapLoading,
  providers,
  pref,
  providerId,
  model,
  onUseDefault,
  onSelectModel,
  onRefreshProvider,
}: {
  bootstrapLoading: boolean;
  providers: ProviderWithModels[];
  pref: UserPreferenceOut | null;
  providerId: string | null;
  model: string | null;
  onUseDefault: () => void;
  onSelectModel: (providerId: string, modelId: string) => void;
  onRefreshProvider: (providerId: string) => void;
}) {
  if (bootstrapLoading) {
    return <ModelSelectorLoading />;
  }

  return (
    <>
      {providers.length === 0 ? (
        <EmptyProvidersHint />
      ) : (
        <>
          <DefaultModelItem
            pref={pref}
            providers={providers}
            onSelect={onUseDefault}
          />
          <DropdownMenuSeparator />
          {providers.map((provider) => (
            <ProviderModelGroup
              key={provider.id}
              provider={provider}
              activeProviderId={providerId}
              activeModel={model}
              onSelectModel={onSelectModel}
              onRefresh={() => onRefreshProvider(provider.id)}
            />
          ))}
          <DropdownMenuSeparator />
        </>
      )}
      <ProviderSettingsLink />
    </>
  );
}

function ModelSelectorLoading() {
  return (
    <div className="flex items-center gap-2 px-2 py-3 text-xs text-muted-foreground">
      <Loader2 className="size-3.5 animate-spin" />
      Loading providers…
    </div>
  );
}

function DefaultModelItem({
  pref,
  providers,
  onSelect,
}: {
  pref: UserPreferenceOut | null;
  providers: ProviderWithModels[];
  onSelect: () => void;
}) {
  return (
    <DropdownMenuItem
      onSelect={(event) => {
        event.preventDefault();
        onSelect();
      }}
      className="gap-2"
    >
      <Sparkles className="text-primary" />
      <div className="flex flex-col">
        <span>Use user default</span>
        <span className="text-[11px] text-muted-foreground">
          {pref?.default_provider_id
            ? `${
                providers.find((provider) => provider.id === pref.default_provider_id)
                  ?.name ?? "—"
              }${pref.default_model ? ` · ${pref.default_model}` : ""}`
            : "No default set — falls back to env config"}
        </span>
      </div>
    </DropdownMenuItem>
  );
}

function ProviderSettingsLink() {
  return (
    <>
      <DropdownMenuLabel className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest">Providers</span>
      </DropdownMenuLabel>
      <DropdownMenuItem asChild>
        <Link href="/settings/providers" className="gap-2">
          <Cog />
          Manage providers
        </Link>
      </DropdownMenuItem>
    </>
  );
}

function EmptyProvidersHint() {
  return (
    <div className="px-3 py-3 text-xs">
      <p className="text-muted-foreground">No LLM providers configured yet.</p>
      <Link
        href="/settings/providers"
        className="mt-1 inline-block font-medium text-primary hover:underline"
      >
        Add your first provider →
      </Link>
    </div>
  );
}
