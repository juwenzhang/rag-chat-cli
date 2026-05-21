"use client";

import { useCallback, useEffect, useState } from "react";

import { Card } from "@/components/ui/card";
import type { ProviderUpdateBody } from "@/lib/api/server/providers";
import type { ModelListItem, ProviderOut } from "@/lib/api/shared/types";

import { ProviderCardDialogs } from "./provider-card-dialogs";
import { ProviderCardHeader } from "./provider-card-header";
import { ProviderModelsPanel } from "./provider-models-panel";

/** One configured provider — header actions + collapsible model list. */
export function ProviderCard({
  provider,
  isUserDefault,
  onPatch,
  onDelete,
  onListModels,
  onDeleteModel,
  onSaveModelDescription,
  onSaveApiKey,
  onClearApiKey,
  onPullModel,
  onError,
  onChanged,
}: {
  provider: ProviderOut;
  isUserDefault: boolean;
  onPatch: (body: ProviderUpdateBody) => Promise<unknown>;
  onDelete: () => Promise<unknown>;
  onListModels: () => Promise<ModelListItem[]>;
  onDeleteModel: (model: string) => Promise<unknown>;
  onSaveModelDescription: (model: string, description: string | null) => Promise<unknown>;
  onSaveApiKey: (apiKey: string) => Promise<unknown>;
  onClearApiKey: () => Promise<unknown>;
  onPullModel: (model: string, signal?: AbortSignal) => Promise<Response>;
  onError: (err: unknown) => void;
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
      setModels(await onListModels());
    } catch (err) {
      setModelsError((err as Error).message);
    } finally {
      setModelsLoading(false);
    }
  }, [onListModels]);

  useEffect(() => {
    if (!modelsOpen || models !== null || modelsLoading) return;
    const id = window.setTimeout(() => void fetchModels(), 0);
    return () => window.clearTimeout(id);
  }, [modelsOpen, models, modelsLoading, fetchModels]);

  const patch = async (body: ProviderUpdateBody) => {
    setBusy(true);
    try {
      await onPatch(body);
      onChanged();
    } catch (err) {
      onError(err);
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async () => {
    setBusy(true);
    try {
      await onDelete();
      onChanged();
    } catch (err) {
      onError(err);
    } finally {
      setBusy(false);
    }
  };

  const doDeleteModel = useCallback(async () => {
    if (!modelToDelete) return;
    try {
      await onDeleteModel(modelToDelete);
      setModelToDelete(null);
      void fetchModels();
    } catch (err) {
      onError(err);
    }
  }, [modelToDelete, onDeleteModel, onError, fetchModels]);

  return (
    <Card>
      <ProviderCardHeader
        provider={provider}
        isUserDefault={isUserDefault}
        busy={busy}
        onOpenApiKey={() => setApiKeyOpen(true)}
        onToggleDefault={() => void patch({ is_default: !provider.is_default })}
        onToggleEnabled={() => void patch({ enabled: !provider.enabled })}
        onRequestDelete={() => setConfirmDelete(true)}
      />

      <ProviderCardDialogs
        provider={provider}
        confirmDelete={confirmDelete}
        pullOpen={pullOpen}
        modelToDelete={modelToDelete}
        modelToEdit={modelToEdit}
        apiKeyOpen={apiKeyOpen}
        onConfirmDeleteOpenChange={setConfirmDelete}
        onPullOpenChange={setPullOpen}
        onDeleteModelOpenChange={(open) => !open && setModelToDelete(null)}
        onEditModelOpenChange={(open) => !open && setModelToEdit(null)}
        onApiKeyOpenChange={(open) => !open && setApiKeyOpen(false)}
        onDelete={doDelete}
        onDeleteModel={doDeleteModel}
        onPullModel={onPullModel}
        onSaveModelDescription={onSaveModelDescription}
        onSaveApiKey={onSaveApiKey}
        onClearApiKey={onClearApiKey}
        onError={onError}
        onModelsChanged={() => void fetchModels()}
        onChanged={onChanged}
        onModelEditDone={() => setModelToEdit(null)}
        onApiKeyDone={() => setApiKeyOpen(false)}
      />

      <ProviderModelsPanel
        provider={provider}
        models={models}
        modelsOpen={modelsOpen}
        modelsLoading={modelsLoading}
        modelsError={modelsError}
        onToggleOpen={() => setModelsOpen((value) => !value)}
        onRefresh={() => void fetchModels()}
        onOpenPull={() => setPullOpen(true)}
        onEditModel={setModelToEdit}
        onDeleteModel={setModelToDelete}
      />
    </Card>
  );
}
