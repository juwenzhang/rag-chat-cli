"use client";

import {
  ArrowLeft,
  Check,
  CloudDownload,
  Download,
  ExternalLink,
  Loader2,
  Pencil,
  Plus,
  RefreshCcw,
  Save,
  Star,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  VirtualTable,
  type VirtualTableColumn,
} from "@/components/ui/virtual-table";
import { PullModelDialog } from "@/components/providers/pull-model-dialog";
import type {
  ModelListItem,
  ProviderOut,
  UserPreferenceOut,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";

interface Props {
  initialProviders: ProviderOut[];
  initialPreferences: UserPreferenceOut;
}

export function ProvidersPageClient({
  initialProviders,
  initialPreferences,
}: Props) {
  const [providers, setProviders] = useState(initialProviders);
  const [pref, setPref] = useState(initialPreferences);
  const [adding, setAdding] = useState(initialProviders.length === 0);

  const refetch = useCallback(async () => {
    try {
      const [p, q] = await Promise.all([
        fetch("/api/providers", { cache: "no-store" }).then((r) => r.json()),
        fetch("/api/me/preferences", { cache: "no-store" }).then((r) => r.json()),
      ]);
      if (Array.isArray(p)) setProviders(p);
      if (q && "default_provider_id" in q) setPref(q);
    } catch (err) {
      toast.error(`Refresh failed: ${(err as Error).message}`);
    }
  }, []);

  return (
    <div className="h-full overflow-y-auto bg-muted/30">
      <div className="mx-auto max-w-3xl space-y-6 px-6 py-10">
        <div className="flex items-center gap-3">
          <Button asChild variant="ghost" size="icon" aria-label="Back to chat">
            <Link href="/chat">
              <ArrowLeft />
            </Link>
          </Button>
          <div className="flex-1">
            <h1 className="text-2xl font-semibold tracking-tight">
              LLM providers
            </h1>
            <p className="text-sm text-muted-foreground">
              Self-host: bring your own Ollama, OpenAI key, or any
              OpenAI-compatible endpoint. Keys are encrypted at rest.
            </p>
          </div>
          {!adding && (
            <Button onClick={() => setAdding(true)} size="sm">
              <Plus /> Add provider
            </Button>
          )}
        </div>

        {adding && (
          <AddProviderForm
            onClose={() => setAdding(false)}
            onCreated={() => {
              setAdding(false);
              void refetch();
            }}
          />
        )}

        <PreferencesCard
          providers={providers}
          pref={pref}
          onUpdated={(p) => setPref(p)}
        />

        <div className="space-y-3">
          {providers.length === 0 && !adding ? (
            <Card>
              <CardContent className="py-10 text-center">
                <p className="text-sm text-muted-foreground">
                  No providers yet. Add one to start chatting.
                </p>
              </CardContent>
            </Card>
          ) : (
            providers.map((p) => (
              <ProviderCard
                key={p.id}
                provider={p}
                isUserDefault={pref.default_provider_id === p.id}
                onChanged={refetch}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add provider form
// ---------------------------------------------------------------------------

function AddProviderForm({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [type, setType] = useState<"ollama" | "openai">("ollama");
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("http://localhost:11434");
  const [apiKey, setApiKey] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [skipTest, setSkipTest] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    detail: string;
  } | null>(null);

  const onTypeChange = (next: "ollama" | "openai") => {
    setType(next);
    setTestResult(null);
    if (next === "ollama" && (!baseUrl || baseUrl.includes("openai"))) {
      setBaseUrl("http://localhost:11434");
    }
    if (next === "openai" && baseUrl.includes("11434")) {
      setBaseUrl("https://api.openai.com/v1");
    }
  };

  const onTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await fetch("/api/providers/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type,
          base_url: baseUrl,
          api_key: apiKey || undefined,
        }),
      });
      const data = (await r.json()) as { ok: boolean; detail: string };
      setTestResult(data);
    } catch (err) {
      setTestResult({ ok: false, detail: (err as Error).message });
    } finally {
      setTesting(false);
    }
  };

  const onSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const r = await fetch("/api/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          type,
          base_url: baseUrl,
          api_key: apiKey || undefined,
          is_default: isDefault,
          test_connectivity: !skipTest,
        }),
      });
      if (!r.ok) {
        const payload = await r.json().catch(() => ({}));
        throw new Error(
          (payload as { message?: string }).message || `HTTP ${r.status}`
        );
      }
      toast.success(`Added provider ${name}`);
      onCreated();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="text-base">Add a provider</CardTitle>
          <CardDescription>
            Type, URL, and (if needed) an API key. We probe the endpoint before
            saving unless you opt out.
          </CardDescription>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Cancel">
          <X />
        </Button>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={onSubmit}>
          <div className="flex gap-2">
            {(["ollama", "openai"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => onTypeChange(t)}
                className={cn(
                  "flex-1 rounded-lg border px-3 py-2 text-sm transition-colors",
                  type === t
                    ? "border-primary bg-primary/5 text-foreground"
                    : "border-border text-muted-foreground hover:bg-muted/40"
                )}
              >
                <div className="font-medium">
                  {t === "ollama" ? "Ollama" : "OpenAI-compatible"}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  {t === "ollama"
                    ? "Local or hosted Ollama"
                    : "OpenAI / OpenRouter / DeepSeek / Together / …"}
                </div>
              </button>
            ))}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                placeholder="local-ollama"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={64}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="base_url">Base URL</Label>
              <Input
                id="base_url"
                value={baseUrl}
                onChange={(e) => {
                  setBaseUrl(e.target.value);
                  setTestResult(null);
                }}
                required
                type="url"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="api_key">
                API key{" "}
                <span className="text-xs text-muted-foreground">
                  ({type === "ollama"
                    ? "optional for local · required for cloud"
                    : "usually required"})
                </span>
              </Label>
              {type === "ollama" && (
                <a
                  href="https://ollama.com/settings/keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground hover:underline"
                >
                  Get your Ollama key
                  <ExternalLink className="size-3" />
                </a>
              )}
            </div>
            <Input
              id="api_key"
              type="password"
              autoComplete="off"
              placeholder={
                type === "ollama"
                  ? "Leave empty for local Ollama · paste key for cloud"
                  : "sk-…"
              }
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value);
                setTestResult(null);
              }}
            />
          </div>

          <div className="flex flex-wrap items-center gap-4 text-sm">
            <label className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={isDefault}
                onChange={(e) => setIsDefault(e.target.checked)}
                className="size-4 rounded border-input"
              />
              Make this my default provider
            </label>
            <label className="inline-flex items-center gap-2 text-muted-foreground">
              <input
                type="checkbox"
                checked={skipTest}
                onChange={(e) => setSkipTest(e.target.checked)}
                className="size-4 rounded border-input"
              />
              Skip connectivity test
            </label>
          </div>

          {testResult && (
            <Alert variant={testResult.ok ? "default" : "destructive"}>
              <AlertDescription className="text-xs">
                {testResult.ok ? "OK — " : "Failed — "}
                {testResult.detail}
              </AlertDescription>
            </Alert>
          )}

          <div className="flex items-center justify-end gap-2 pt-1">
            <Button
              type="button"
              variant="outline"
              onClick={onTest}
              disabled={testing || !baseUrl}
            >
              {testing ? (
                <Loader2 className="animate-spin" />
              ) : (
                <RefreshCcw />
              )}
              Test connection
            </Button>
            <Button type="submit" disabled={submitting || !name.trim()}>
              {submitting ? <Loader2 className="animate-spin" /> : <Plus />}
              Add provider
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Existing-provider card
// ---------------------------------------------------------------------------

function ProviderCard({
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

  const fetchModels = useCallback(async () => {
    setModelsLoading(true);
    setModelsError(null);
    try {
      const r = await fetch(`/api/providers/${provider.id}/models`, {
        cache: "no-store",
      });
      const data = (await r.json()) as ModelListItem[] | { error: string };
      if (Array.isArray(data)) setModels(data);
      else
        setModelsError(
          (data as { message?: string }).message || "Failed to load"
        );
    } catch (err) {
      setModelsError((err as Error).message);
    } finally {
      setModelsLoading(false);
    }
  }, [provider.id]);

  useEffect(() => {
    if (modelsOpen && models === null && !modelsLoading) void fetchModels();
  }, [modelsOpen, models, modelsLoading, fetchModels]);

  const patch = async (body: Record<string, unknown>) => {
    setBusy(true);
    try {
      const r = await fetch(`/api/providers/${provider.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const payload = await r.json().catch(() => ({}));
        throw new Error(
          (payload as { message?: string }).message || `HTTP ${r.status}`
        );
      }
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
      const r = await fetch(`/api/providers/${provider.id}`, {
        method: "DELETE",
      });
      if (!r.ok) {
        const payload = await r.json().catch(() => ({}));
        throw new Error(
          (payload as { message?: string }).message || `HTTP ${r.status}`
        );
      }
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
      const r = await fetch(`/api/providers/${provider.id}/models/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: modelToDelete }),
      });
      if (!r.ok) {
        const payload = await r.json().catch(() => ({}));
        throw new Error(
          (payload as { message?: string }).message || `HTTP ${r.status}`
        );
      }
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
            {provider.has_api_key && (
              <span className="ml-2 inline-flex items-center gap-1 text-[10px]">
                <Check className="size-3 text-success" />
                API key stored
              </span>
            )}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
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

// ---------------------------------------------------------------------------
// Preferences (default provider/model + RAG default)
// ---------------------------------------------------------------------------

function PreferencesCard({
  providers,
  pref,
  onUpdated,
}: {
  providers: ProviderOut[];
  pref: UserPreferenceOut;
  onUpdated: (p: UserPreferenceOut) => void;
}) {
  const [providerId, setProviderId] = useState<string | null>(
    pref.default_provider_id
  );
  const [modelName, setModelName] = useState(pref.default_model ?? "");
  const [embeddingModel, setEmbeddingModel] = useState(
    pref.default_embedding_model ?? ""
  );
  const [useRag, setUseRag] = useState(pref.default_use_rag);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setProviderId(pref.default_provider_id);
    setModelName(pref.default_model ?? "");
    setEmbeddingModel(pref.default_embedding_model ?? "");
    setUseRag(pref.default_use_rag);
  }, [pref]);

  const save = async () => {
    setBusy(true);
    try {
      const r = await fetch("/api/me/preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          default_provider_id: providerId ?? undefined,
          clear_default_provider: providerId === null,
          default_model: modelName.trim() ? modelName.trim() : undefined,
          clear_default_model: !modelName.trim(),
          default_embedding_model: embeddingModel.trim()
            ? embeddingModel.trim()
            : undefined,
          clear_default_embedding_model: !embeddingModel.trim(),
          default_use_rag: useRag,
        }),
      });
      if (!r.ok) {
        const payload = await r.json().catch(() => ({}));
        throw new Error(
          (payload as { message?: string }).message || `HTTP ${r.status}`
        );
      }
      const data = (await r.json()) as UserPreferenceOut;
      onUpdated(data);
      toast.success("Preferences saved");
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const dirty =
    providerId !== pref.default_provider_id ||
    (modelName.trim() || null) !== (pref.default_model || null) ||
    (embeddingModel.trim() || null) !==
      (pref.default_embedding_model || null) ||
    useRag !== pref.default_use_rag;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Defaults</CardTitle>
        <CardDescription>
          Applied to every new chat session that doesn&apos;t pin its own
          provider or model.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="default_provider">Default provider</Label>
            <select
              id="default_provider"
              value={providerId ?? ""}
              onChange={(e) => setProviderId(e.target.value || null)}
              className={cn(
                "flex h-10 w-full rounded-lg border border-input bg-background px-3 text-sm",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              )}
            >
              <option value="">— None (use first available) —</option>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.type})
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="default_model">Default chat model</Label>
            <Input
              id="default_model"
              placeholder="qwen2.5:1.5b"
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              maxLength={128}
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="default_embedding_model">
            Default embedding model{" "}
            <span className="text-xs font-normal text-muted-foreground">
              (used for RAG ingest &amp; retrieval, not chat)
            </span>
          </Label>
          <EmbeddingModelSelect
            providers={providers}
            value={embeddingModel}
            onChange={setEmbeddingModel}
          />
          <p className="text-[11px] text-muted-foreground">
            Auto-populated from your providers — only models classified as
            embedding (e.g. <code className="font-mono">nomic-embed-text</code>,{" "}
            <code className="font-mono">bge-m3</code>) appear. Pull one from the
            provider card below if the list is empty.
          </p>
        </div>
        <Separator />
        <label className="flex items-center justify-between text-sm">
          <div>
            <p className="font-medium">RAG by default</p>
            <p className="text-xs text-muted-foreground">
              Toggle retrieval for new chat sessions. Note: web upload UI lands
              in the next sprint — until then the toggle has no effect on chat
              from the web.
            </p>
          </div>
          <input
            type="checkbox"
            checked={useRag}
            onChange={(e) => setUseRag(e.target.checked)}
            className="size-4 rounded border-input"
          />
        </label>
        <div className="flex justify-end">
          <Button onClick={save} disabled={busy || !dirty}>
            {busy ? <Loader2 className="animate-spin" /> : <Save />}
            Save defaults
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Model list table — modern, virtualised, dynamic row heights
// ---------------------------------------------------------------------------

function ModelTable({
  models,
  providerType,
  onEdit,
  onDelete,
}: {
  models: ModelListItem[];
  providerType: string;
  onEdit: (model: ModelListItem) => void;
  onDelete: (modelId: string) => void;
}) {
  const isOllama = providerType === "ollama";

  const columns: VirtualTableColumn<ModelListItem>[] = [
    {
      key: "name",
      header: "Model",
      width: "minmax(220px, 2.5fr)",
      cell: (m) => (
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="truncate font-mono text-[13px] text-foreground">
            {m.id}
          </span>
          {m.kind === "embedding" && (
            <Badge
              variant="secondary"
              className="shrink-0 px-1 py-0 text-[9px] uppercase tracking-wide"
            >
              embed
            </Badge>
          )}
          {m.id.toLowerCase().endsWith("-cloud") && (
            <Badge
              variant="outline"
              className="shrink-0 gap-1 px-1 py-0 text-[9px] uppercase tracking-wide text-primary"
            >
              <CloudDownload className="size-2.5" />
              cloud
            </Badge>
          )}
        </div>
      ),
    },
    {
      key: "size",
      header: "Size",
      width: "84px",
      align: "right",
      cell: (m) =>
        m.size != null ? (
          <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
            {formatSize(m.size)}
          </span>
        ) : (
          <span className="text-[11px] text-muted-foreground/50">—</span>
        ),
    },
    {
      key: "desc",
      header: "Description",
      width: "minmax(0, 3fr)",
      cell: (m) =>
        m.description ? (
          <span
            className="line-clamp-2 text-[12px] leading-snug text-muted-foreground"
            title={m.description}
          >
            {m.description}
          </span>
        ) : (
          <button
            type="button"
            onClick={() => onEdit(m)}
            className="text-[11px] italic text-muted-foreground/60 underline-offset-2 hover:text-foreground hover:underline"
          >
            add a note…
          </button>
        ),
    },
    {
      key: "actions",
      header: "",
      width: isOllama ? "76px" : "44px",
      align: "right",
      cell: (m) => (
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onEdit(m);
            }}
            aria-label={`Edit description for ${m.id}`}
            className="rounded-md p-1.5 text-muted-foreground/70 transition-colors hover:bg-foreground/10 hover:text-foreground"
          >
            <Pencil className="size-3.5" />
          </button>
          {isOllama && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(m.id);
              }}
              aria-label={`Delete model ${m.id}`}
              className="rounded-md p-1.5 text-muted-foreground/70 transition-colors hover:bg-destructive/10 hover:text-destructive"
            >
              <Trash2 className="size-3.5" />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <VirtualTable
      rows={models}
      rowKey={(m) => m.id}
      columns={columns}
      estimatedRowHeight={48}
      maxHeight={420}
      density="comfortable"
    />
  );
}

// ---------------------------------------------------------------------------
// Edit-description dialog (per (provider, model))
// ---------------------------------------------------------------------------

function EditDescriptionDialog({
  providerId,
  model,
  onOpenChange,
  onSaved,
}: {
  providerId: string;
  model: ModelListItem | null;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setText(model?.description ?? "");
  }, [model]);

  const save = async () => {
    if (!model) return;
    setSaving(true);
    try {
      const r = await fetch(`/api/providers/${providerId}/models/meta`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: model.id,
          description: text.trim() || null,
        }),
      });
      if (!r.ok) {
        const payload = await r.json().catch(() => ({}));
        throw new Error(
          (payload as { message?: string }).message || `HTTP ${r.status}`
        );
      }
      toast.success("Description saved");
      onSaved();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={model !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Edit description</DialogTitle>
          <DialogDescription>
            Free text shown on hover in the model picker. Empty clears it.
          </DialogDescription>
        </DialogHeader>
        {model && (
          <>
            <div className="space-y-1.5">
              <Label htmlFor="model_desc" className="font-mono text-xs">
                {model.id}
              </Label>
              <Textarea
                id="model_desc"
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={4}
                maxLength={2000}
                placeholder="What is this model for?"
                className="resize-none"
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => onOpenChange(false)}
                disabled={saving}
              >
                Cancel
              </Button>
              <Button onClick={save} disabled={saving}>
                {saving ? <Loader2 className="animate-spin" /> : <Save />}
                Save
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Embedding-model dropdown — only lists models with `kind === "embedding"`
// across the user's enabled providers, in one round-trip per provider.
// ---------------------------------------------------------------------------

function EmbeddingModelSelect({
  providers,
  value,
  onChange,
}: {
  providers: ProviderOut[];
  value: string;
  onChange: (next: string) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [grouped, setGrouped] = useState<
    Array<{ providerName: string; models: ModelListItem[] }>
  >([]);

  useEffect(() => {
    const enabled = providers.filter((p) => p.enabled);
    if (enabled.length === 0) {
      setGrouped([]);
      return;
    }
    setLoading(true);
    void (async () => {
      try {
        const results = await Promise.all(
          enabled.map(async (p) => {
            const r = await fetch(`/api/providers/${p.id}/models`, {
              cache: "no-store",
            });
            const data = (await r.json()) as ModelListItem[] | { error: string };
            const items = Array.isArray(data) ? data : [];
            return {
              providerName: p.name,
              models: items.filter((m) => m.kind === "embedding"),
            };
          })
        );
        setGrouped(results.filter((g) => g.models.length > 0));
      } finally {
        setLoading(false);
      }
    })();
  }, [providers]);

  const totalCount = grouped.reduce((sum, g) => sum + g.models.length, 0);
  // Show free-text fallback when the typed value isn't in the discovered list
  // (e.g. user pasted a tag the provider hasn't pulled yet).
  const valueInList = grouped.some((g) =>
    g.models.some((m) => m.id === value)
  );

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
      {value && !valueInList && (
        <option value={value}>{value} (not installed)</option>
      )}
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
