"use client";

import { Loader2, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

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
import { api } from "@/lib/api/browser";
import type { ProviderOut, UserPreferenceOut } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { EmbeddingModelSelect } from "./embedding-model-select";

/** User defaults card — default provider/model, embedding model, RAG toggle. */
export function PreferencesCard({
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
      const data = await api.me.updatePreferences({
        default_provider_id: providerId ?? undefined,
        clear_default_provider: providerId === null,
        default_model: modelName.trim() ? modelName.trim() : undefined,
        clear_default_model: !modelName.trim(),
        default_embedding_model: embeddingModel.trim()
          ? embeddingModel.trim()
          : undefined,
        clear_default_embedding_model: !embeddingModel.trim(),
        default_use_rag: useRag,
      });
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
