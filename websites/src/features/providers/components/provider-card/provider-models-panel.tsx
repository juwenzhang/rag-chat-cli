"use client";

import { Download, Loader2, RefreshCcw } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { CardContent } from "@/components/ui/card";
import type { ModelListItem, ProviderOut } from "@/lib/api/shared/types";
import { cn } from "@/lib/utils";

import { ModelTable } from "../model-table";

export function ProviderModelsPanel({
  provider,
  models,
  modelsOpen,
  modelsLoading,
  modelsError,
  onToggleOpen,
  onRefresh,
  onOpenPull,
  onEditModel,
  onDeleteModel,
}: {
  provider: ProviderOut;
  models: ModelListItem[] | null;
  modelsOpen: boolean;
  modelsLoading: boolean;
  modelsError: string | null;
  onToggleOpen: () => void;
  onRefresh: () => void;
  onOpenPull: () => void;
  onEditModel: (model: ModelListItem) => void;
  onDeleteModel: (modelId: string) => void;
}) {
  return (
    <CardContent className="pt-0">
      <div className="flex w-full items-center justify-between gap-2 text-sm">
        <button
          type="button"
          className="flex-1 text-left text-muted-foreground hover:text-foreground"
          onClick={onToggleOpen}
        >
          {modelsOpen ? "Hide models" : "Show models"}
          {models ? ` (${models.length})` : ""}
        </button>
        {modelsOpen && (
          <button
            type="button"
            onClick={onRefresh}
            className="rounded p-1 text-muted-foreground/70 hover:bg-foreground/5 hover:text-foreground"
            aria-label="Refresh models"
          >
            <RefreshCcw
              className={cn("size-3.5", modelsLoading && "animate-spin")}
            />
          </button>
        )}
        {provider.type === "ollama" && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onOpenPull}
            className="h-7 gap-1.5 text-xs"
          >
            <Download className="size-3.5" />
            Pull model
          </Button>
        )}
      </div>
      {modelsOpen && (
        <div className="mt-3">
          <ProviderModelsContent
            providerType={provider.type}
            models={models}
            loading={modelsLoading}
            error={modelsError}
            onEditModel={onEditModel}
            onDeleteModel={onDeleteModel}
          />
        </div>
      )}
    </CardContent>
  );
}

function ProviderModelsContent({
  providerType,
  models,
  loading,
  error,
  onEditModel,
  onDeleteModel,
}: {
  providerType: ProviderOut["type"];
  models: ModelListItem[] | null;
  loading: boolean;
  error: string | null;
  onEditModel: (model: ModelListItem) => void;
  onDeleteModel: (modelId: string) => void;
}) {
  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription className="text-xs">{error}</AlertDescription>
      </Alert>
    );
  }

  if (loading && !models) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="size-3 animate-spin" /> Loading models…
      </div>
    );
  }

  if (models && models.length > 0) {
    return (
      <ModelTable
        models={models}
        providerType={providerType}
        onEdit={onEditModel}
        onDelete={onDeleteModel}
      />
    );
  }

  return (
    <p className="text-xs text-muted-foreground">
      No models exposed by this endpoint.
    </p>
  );
}
