"use client";

import { Cpu, Loader2, RefreshCcw } from "lucide-react";
import Link from "next/link";

import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import type { ModelListItem } from "@/lib/api/shared/types";
import { cn } from "@/lib/utils";

import type { ProviderWithModels } from "./model-selector-menu";

export function ProviderModelGroup({
  provider,
  activeProviderId,
  activeModel,
  onSelectModel,
  onRefresh,
}: {
  provider: ProviderWithModels;
  activeProviderId: string | null;
  activeModel: string | null;
  onSelectModel: (providerId: string, modelId: string) => void;
  onRefresh: () => void;
}) {
  return (
    <div className="px-1 py-1">
      <ProviderModelHeader provider={provider} onRefresh={onRefresh} />
      <ProviderModels
        provider={provider}
        activeProviderId={activeProviderId}
        activeModel={activeModel}
        onSelectModel={onSelectModel}
      />
    </div>
  );
}

function ProviderModelHeader({
  provider,
  onRefresh,
}: {
  provider: ProviderWithModels;
  onRefresh: () => void;
}) {
  return (
    <div className="flex items-center justify-between px-1 py-1">
      <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
        <span>{provider.name}</span>
        <span className="rounded bg-muted px-1 py-0.5 text-[9px] uppercase tracking-wide">
          {provider.type}
        </span>
      </div>
      <button
        type="button"
        onClick={(event) => {
          event.preventDefault();
          onRefresh();
        }}
        aria-label="Refresh models"
        className="rounded p-0.5 text-muted-foreground/70 hover:bg-foreground/5 hover:text-foreground"
      >
        <RefreshCcw className={cn("size-3", provider.modelsLoading && "animate-spin")} />
      </button>
    </div>
  );
}

function ProviderModels({
  provider,
  activeProviderId,
  activeModel,
  onSelectModel,
}: {
  provider: ProviderWithModels;
  activeProviderId: string | null;
  activeModel: string | null;
  onSelectModel: (providerId: string, modelId: string) => void;
}) {
  if (provider.modelsError) {
    return (
      <div className="px-2 py-1.5 text-[11px] text-destructive">
        {provider.modelsError}
      </div>
    );
  }
  if (provider.modelsLoading && !provider.models) {
    return (
      <div className="flex items-center gap-2 px-2 py-1.5 text-[11px] text-muted-foreground">
        <Loader2 className="size-3 animate-spin" />
        Loading models…
      </div>
    );
  }
  if (!provider.models || provider.models.length === 0) {
    return (
      <div className="px-2 py-1.5 text-[11px] text-muted-foreground">
        No models exposed.
      </div>
    );
  }

  const chatModels = provider.models.filter((item) => item.kind === "chat" || !item.kind);
  const embedCount = provider.models.filter((item) => item.kind === "embedding").length;
  const visionCount = provider.models.filter((item) => item.kind === "vision").length;

  return (
    <>
      {chatModels.length === 0 ? (
        <div className="px-2 py-1.5 text-[11px] text-muted-foreground">
          No chat models — only embedding models are installed.
        </div>
      ) : (
        chatModels.map((item) => (
          <ModelOption
            key={item.id}
            model={item}
            active={activeProviderId === provider.id && activeModel === item.id}
            onSelect={() => onSelectModel(provider.id, item.id)}
          />
        ))
      )}
      {embedCount > 0 && <HiddenEmbeddingNote count={embedCount} />}
      {visionCount > 0 && <HiddenVisionNote count={visionCount} />}
    </>
  );
}

function ModelOption({
  model,
  active,
  onSelect,
}: {
  model: ModelListItem;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <DropdownMenuItem
      onSelect={(event) => {
        event.preventDefault();
        onSelect();
      }}
      title={model.description ?? undefined}
      className={cn(
        "flex-col items-start gap-0.5 pl-3 text-[12.5px]",
        active && "bg-accent/60"
      )}
    >
      <div className="flex w-full items-center gap-2">
        <Cpu
          className={cn("size-3.5", active ? "text-primary" : "text-muted-foreground")}
        />
        <span className="truncate">{model.id}</span>
        {model.size != null && (
          <span className="ml-auto text-[10px] text-muted-foreground">
            {formatSize(model.size)}
          </span>
        )}
      </div>
      {model.description && (
        <span className="line-clamp-2 pl-5 text-[10.5px] font-normal text-muted-foreground">
          {model.description}
        </span>
      )}
    </DropdownMenuItem>
  );
}

function HiddenEmbeddingNote({ count }: { count: number }) {
  return (
    <div className="px-3 py-1 text-[10px] text-muted-foreground/80">
      +{count} embedding model{count === 1 ? "" : "s"} hidden — set under{" "}
      <Link href="/settings/providers" className="underline hover:text-foreground">
        Settings
      </Link>
    </div>
  );
}

function HiddenVisionNote({ count }: { count: number }) {
  return (
    <div className="px-3 py-1 text-[10px] text-muted-foreground/80">
      +{count} vision model{count === 1 ? "" : "s"} hidden — used by image features
    </div>
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
