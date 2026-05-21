"use client";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { ModelListItem, ProviderOut } from "@/lib/api/shared/types";

import { EditApiKeyDialog } from "../edit-api-key-dialog";
import { EditDescriptionDialog } from "../edit-description-dialog";
import { PullModelDialog } from "../pull-model-dialog";

export function ProviderCardDialogs({
  provider,
  confirmDelete,
  pullOpen,
  modelToDelete,
  modelToEdit,
  apiKeyOpen,
  onConfirmDeleteOpenChange,
  onPullOpenChange,
  onDeleteModelOpenChange,
  onEditModelOpenChange,
  onApiKeyOpenChange,
  onDelete,
  onDeleteModel,
  onPullModel,
  onSaveModelDescription,
  onSaveApiKey,
  onClearApiKey,
  onError,
  onModelsChanged,
  onChanged,
  onModelEditDone,
  onApiKeyDone,
}: {
  provider: ProviderOut;
  confirmDelete: boolean;
  pullOpen: boolean;
  modelToDelete: string | null;
  modelToEdit: ModelListItem | null;
  apiKeyOpen: boolean;
  onConfirmDeleteOpenChange: (open: boolean) => void;
  onPullOpenChange: (open: boolean) => void;
  onDeleteModelOpenChange: (open: boolean) => void;
  onEditModelOpenChange: (open: boolean) => void;
  onApiKeyOpenChange: (open: boolean) => void;
  onDelete: () => Promise<void>;
  onDeleteModel: () => Promise<void>;
  onPullModel: (model: string, signal?: AbortSignal) => Promise<Response>;
  onSaveModelDescription: (model: string, description: string | null) => Promise<unknown>;
  onSaveApiKey: (apiKey: string) => Promise<unknown>;
  onClearApiKey: () => Promise<unknown>;
  onError: (err: unknown) => void;
  onModelsChanged: () => void;
  onChanged: () => void;
  onModelEditDone: () => void;
  onApiKeyDone: () => void;
}) {
  return (
    <>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={onConfirmDeleteOpenChange}
        title={`Delete provider "${provider.name}"?`}
        description={
          <>
            This will remove the saved endpoint and any encrypted API key. Chat
            sessions pinned to this provider will fall back to your user default.
          </>
        }
        confirmLabel="Delete"
        destructive
        onConfirm={onDelete}
      />
      <PullModelDialog
        providerName={provider.name}
        open={pullOpen}
        onOpenChange={onPullOpenChange}
        onPullModel={onPullModel}
        onSaveDescription={onSaveModelDescription}
        onPulled={() => {
          onModelsChanged();
          onChanged();
        }}
      />
      <ConfirmDialog
        open={modelToDelete !== null}
        onOpenChange={onDeleteModelOpenChange}
        title={`Remove "${modelToDelete}" from Ollama?`}
        description={
          <>
            This calls Ollama&apos;s <code className="font-mono">/api/delete</code>{" "}
            and frees the disk space the model layers occupied. Pulling it again
            later will re-download.
          </>
        }
        confirmLabel="Remove"
        destructive
        onConfirm={onDeleteModel}
      />
      <EditDescriptionDialog
        model={modelToEdit}
        onOpenChange={onEditModelOpenChange}
        onSaveDescription={onSaveModelDescription}
        onError={onError}
        onSaved={() => {
          onModelEditDone();
          onModelsChanged();
        }}
      />
      <EditApiKeyDialog
        provider={apiKeyOpen ? provider : null}
        onOpenChange={onApiKeyOpenChange}
        onSaveKey={onSaveApiKey}
        onClearKey={onClearApiKey}
        onError={onError}
        onSaved={() => {
          onApiKeyDone();
          onChanged();
        }}
      />
    </>
  );
}
