"use client";

import { ArrowLeft, Plus } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { providerService } from "@/features/providers/services/provider-service";
import { useProvidersStore } from "@/features/providers/stores/providers-store";
import type { ProviderOut, UserPreferenceOut } from "@/lib/api/shared/types";

import { AddProviderForm } from "./add-provider-form";
import { PreferencesCard } from "./preferences-card";
import { ProviderCard } from "./provider-card";

interface Props {
  initialProviders: ProviderOut[];
  initialPreferences: UserPreferenceOut;
}

/** Providers settings controller — owns API orchestration and passes pure callbacks to views. */
export function ProvidersPageClient({
  initialProviders,
  initialPreferences,
}: Props) {
  const providers = useProvidersStore((state) => state.providers);
  const pref = useProvidersStore((state) => state.preferences);
  const adding = useProvidersStore((state) => state.adding);
  const init = useProvidersStore((state) => state.init);
  const setProviders = useProvidersStore((state) => state.setProviders);
  const setPreferences = useProvidersStore((state) => state.setPreferences);
  const setAdding = useProvidersStore((state) => state.setAdding);

  useEffect(() => {
    init({ providers: initialProviders, preferences: initialPreferences });
  }, [init, initialPreferences, initialProviders]);

  const refetch = useCallback(async () => {
    try {
      const [nextProviders, nextPreferences] = await providerService.loadSettings();
      setProviders(nextProviders);
      setPreferences(nextPreferences);
    } catch (err) {
      toast.error(`Refresh failed: ${(err as Error).message}`);
    }
  }, [setPreferences, setProviders]);

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
            onTestConnection={providerService.test}
            onCreate={async (body) => {
              const created = await providerService.create(body);
              toast.success(`Added provider ${body.name}`);
              return created;
            }}
            onCreated={() => {
              setAdding(false);
              void refetch();
            }}
          />
        )}

        <PreferencesCard
          providers={providers}
          pref={pref}
          onSave={async (body) => {
            const next = await providerService.updatePreferences(body);
            toast.success("Preferences saved");
            return next;
          }}
          onLoadEmbeddingModels={providerService.listEmbeddingModels}
          onError={(err) => toast.error((err as Error).message)}
          onUpdated={setPreferences}
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
                onPatch={async (body) => {
                  const updated = await providerService.update(p.id, body);
                  toast.success("Provider updated");
                  return updated;
                }}
                onDelete={async () => {
                  await providerService.remove(p.id);
                  toast.success(`Deleted ${p.name}`);
                }}
                onListModels={() => providerService.listModels(p.id)}
                onDeleteModel={async (model) => {
                  await providerService.deleteModel(p.id, model);
                  toast.success(`Removed ${model}`);
                }}
                onSaveModelDescription={async (model, description) => {
                  await providerService.saveModelDescription(p.id, model, description);
                  toast.success("Description saved");
                }}
                onSaveApiKey={async (apiKey) => {
                  await providerService.saveApiKey(p.id, apiKey);
                  toast.success("API key saved");
                }}
                onClearApiKey={async () => {
                  await providerService.clearApiKey(p.id);
                  toast.success("API key cleared");
                }}
                onPullModel={async (model, signal) => {
                  const response = await providerService.pullModel(p.id, model, signal);
                  return response;
                }}
                onError={(err) => toast.error((err as Error).message)}
                onChanged={refetch}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
