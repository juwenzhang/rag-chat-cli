"use client";

import {
  Check,
  Download,
  Key,
  Loader2,
  RefreshCcw,
  Star,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { api } from "@/lib/api/browser";
import type { ProviderUpdateBody } from "@/lib/api/providers";
import type { ModelListItem, ProviderOut } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { EditApiKeyDialog } from "./edit-api-key-dialog";
import { EditDescriptionDialog } from "./edit-description-dialog";
import { ModelTable } from "./model-table";
import { PullModelDialog } from "./pull-model-dialog";

/** One configured provider — header actions + collapsible model list. */
export function ProviderCard({
  provider,
  isUserDefault,
  onChanged,
}: {
  provider: ProviderOut;
  isUserDefault: boolean;
  onChanged: () => void;
}) {
  const [models, setModels] = useState<ModelListItem[] | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [modelsOpen, setModelsOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [pullOpen, setPullOpen] = useState(false);
  const [modelToDelete, setModelToDelete] = useState<string | null>(null);
  const [modelToEdit, setModelToEdit] = useState<ModelListItem | null>(null);
  const [apiKeyOpen, setApiKeyOpen] = useState(false);

  const fetchModels = useCallback(async () => {
    setModelsLoading(true);
    setModelsError(null);
    try {
      setModels(await api.providers.listModels(provider.id));
    } catch (err) {
      setModelsError((err as Error).message);
    } finally {
      setModelsLoading(false);
    }
  }, [provider.id]);

  useEffect(() => {
    if (modelsOpen && models === null && !modelsLoading) void fetchModels();
  }, [modelsOpen, models, modelsLoading, fetchModels]);

  const patch = async (body: ProviderUpdateBody) => {
    setBusy(true);
    try {
      await api.providers.update(provider.id, body);
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async () => {
    setBusy(true);
    try {
      await api.providers.remove(provider.id);
      toast.success(`Deleted ${provider.name}`);
      onChanged();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const doDeleteModel = useCallback(async () => {
    if (!modelToDelete) return;
    try {
      await api.providers.deleteModel(provider.id, modelToDelete);
      toast.success(`Removed ${modelToDelete}`);
      setModelToDelete(null);
      void fetchModels();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }, [modelToDelete, provider.id, fetchModels]);

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between space-y-0 gap-3">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-base font-medium">{provider.name}</h3>
            <Badge variant="outline" className="text-[10px] uppercase">
              {provider.type}
            </Badge>
            {provider.is_default && (
              <Badge variant="success" className="gap-1 text-[10px]">
                <Star className="size-3" />
                default
              </Badge>
            )}
            {!provider.enabled && (
              <Badge variant="secondary" className="text-[10px]">
                disabled
              </Badge>
            )}
            {isUserDefault && !provider.is_default && (
              <Badge variant="secondary" className="text-[10px]">
                user default
              </Badge>
            )}
          </div>
          <p className="truncate text-xs text-muted-foreground">
            {provider.base_url}
            <button
              type="button"
              onClick={() => setApiKeyOpen(true)}
              className={cn(
                "ml-2 inline-flex items-center gap-1 text-[10px] transition-colors hover:text-foreground",
                provider.has_api_key ? "text-success" : "text-muted-foreground/60"
              )}
            >
              {provider.has_api_key ? (
                <>
                  <Check className="size-3" />
                  API key stored
                </>
              ) : (
                <>
                  <Key className="size-3" />
                  Set API key
                </>
              )}
            </button>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant={provider.has_api_key ? "ghost" : "outline"}
            size="sm"
            onClick={() => setApiKeyOpen(true)}
            disabled={busy}
          >
            <Key className={cn("size-3.5", provider.has_api_key && "text-success")} />
            <span className="hidden sm:inline">
              {provider.has_api_key ? "API Key" : "Set API Key"}
            </span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => patch({ is_default: !provider.is_default })}
            disabled={busy}
          >
            <Star
              className={cn(provider.is_default && "fill-current text-yellow-500")}
            />
            <span className="hidden sm:inline">
              {provider.is_default ? "Unset default" : "Make default"}
            </span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => patch({ enabled: !provider.enabled })}
            disabled={busy}
          >
            {provider.enabled ? "Disable" : "Enable"}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setConfirmDelete(true)}
            disabled={busy}
            aria-label="Delete provider"
          >
            <Trash2 />
          </Button>
        </div>
      </CardHeader>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete provider "${provider.name}"?`}
        description={
          <>
            This will remove the saved endpoint and any encrypted API key. Chat
            sessions pinned to this provider will fall back to your user default.
          </>
        }
        confirmLabel="Delete"
        destructive
        onConfirm={doDelete}
      />
      <PullModelDialog
        providerId={provider.id}
        providerName={provider.name}
        open={pullOpen}
        onOpenChange={setPullOpen}
        onPulled={() => {
          void fetchModels();
          onChanged();
        }}
      />
      <ConfirmDialog
        open={modelToDelete !== null}
        onOpenChange={(o) => !o && setModelToDelete(null)}
        title={`Remove "${modelToDelete}" from Ollama?`}
        description={
          <>
            This calls Ollama&apos;s <code className="font-mono">/api/delete</code>{" "}
            and frees the disk space the model layers occupied. Pulling it
            again later will re-download.
          </>
        }
        confirmLabel="Remove"
        destructive
        onConfirm={doDeleteModel}
      />
      <EditDescriptionDialog
        providerId={provider.id}
        model={modelToEdit}
        onOpenChange={(o) => !o && setModelToEdit(null)}
        onSaved={() => {
          setModelToEdit(null);
          void fetchModels();
        }}
      />
      <EditApiKeyDialog
        provider={apiKeyOpen ? provider : null}
        onOpenChange={(o) => !o && setApiKeyOpen(false)}
        onSaved={() => {
          setApiKeyOpen(false);
          onChanged();
        }}
      />
      <CardContent className="pt-0">
        <div className="flex w-full items-center justify-between gap-2 text-sm">
          <button
            type="button"
            className="flex-1 text-left text-muted-foreground hover:text-foreground"
            onClick={() => setModelsOpen((v) => !v)}
          >
            {modelsOpen ? "Hide models" : "Show models"}
            {models ? ` (${models.length})` : ""}
          </button>
          {modelsOpen && (
            <button
              type="button"
              onClick={() => void fetchModels()}
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
              onClick={() => setPullOpen(true)}
              className="h-7 gap-1.5 text-xs"
            >
              <Download className="size-3.5" />
              Pull model
            </Button>
          )}
        </div>
        {modelsOpen && (
          <div className="mt-3">
            {modelsError ? (
              <Alert variant="destructive">
                <AlertDescription className="text-xs">
                  {modelsError}
                </AlertDescription>
              </Alert>
            ) : modelsLoading && !models ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="size-3 animate-spin" /> Loading models…
              </div>
            ) : models && models.length > 0 ? (
              <ModelTable
                models={models}
                providerType={provider.type}
                onEdit={(m) => setModelToEdit(m)}
                onDelete={(id) => setModelToDelete(id)}
              />
            ) : (
              <p className="text-xs text-muted-foreground">
                No models exposed by this endpoint.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
