"use client";

import {
  ArrowLeft,
  Check,
  Loader2,
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
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
            <Label htmlFor="api_key">
              API key{" "}
              <span className="text-xs text-muted-foreground">
                ({type === "ollama" ? "optional for local" : "usually required"})
              </span>
            </Label>
            <Input
              id="api_key"
              type="password"
              autoComplete="off"
              placeholder={
                type === "ollama" ? "Leave empty for local Ollama" : "sk-…"
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

  const remove = async () => {
    if (!confirm(`Delete provider "${provider.name}"?`)) return;
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
            onClick={remove}
            disabled={busy}
            aria-label="Delete provider"
          >
            <Trash2 />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <button
          type="button"
          className="flex w-full items-center justify-between text-sm text-muted-foreground hover:text-foreground"
          onClick={() => setModelsOpen((v) => !v)}
        >
          <span>
            {modelsOpen ? "Hide models" : "Show models"}
            {models ? ` (${models.length})` : ""}
          </span>
          {modelsOpen && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                void fetchModels();
              }}
              className="rounded p-1 text-muted-foreground/70 hover:bg-foreground/5 hover:text-foreground"
              aria-label="Refresh models"
            >
              <RefreshCcw
                className={cn("size-3.5", modelsLoading && "animate-spin")}
              />
            </button>
          )}
        </button>
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
              <ul className="grid gap-1 sm:grid-cols-2">
                {models.map((m) => (
                  <li
                    key={m.id}
                    className="flex items-center justify-between rounded-md border border-border bg-muted/30 px-2.5 py-1.5"
                  >
                    <span className="truncate text-xs font-mono">{m.id}</span>
                    {m.size != null && (
                      <span className="text-[10px] text-muted-foreground">
                        {formatSize(m.size)}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
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
  const [useRag, setUseRag] = useState(pref.default_use_rag);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setProviderId(pref.default_provider_id);
    setModelName(pref.default_model ?? "");
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
            <Label htmlFor="default_model">Default model</Label>
            <Input
              id="default_model"
              placeholder="qwen2.5:1.5b"
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              maxLength={128}
            />
          </div>
        </div>
        <Separator />
        <label className="flex items-center justify-between text-sm">
          <div>
            <p className="font-medium">RAG by default</p>
            <p className="text-xs text-muted-foreground">
              Toggle retrieval for new chat sessions automatically.
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
