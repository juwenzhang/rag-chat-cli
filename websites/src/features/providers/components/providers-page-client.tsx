"use client";

import { Plus } from "lucide-react";
import { useCallback, useEffect } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { providerService } from "@/features/providers/services/provider-service";
import { useProvidersStore } from "@/features/providers/stores/providers-store";
import type { ProviderOut, UserPreferenceOut } from "@/lib/api/shared/types";
import { useI18n } from "@/lib/i18n/provider";

import { AddProviderForm } from "./add-provider-form";
import { PreferencesCard } from "./preferences-card";
import { ProviderCard } from "./provider-card";

interface Props {
  initialProviders: ProviderOut[];
  initialPreferences: UserPreferenceOut;
}

/** Providers settings controller — owns API orchestration and passes pure callbacks to views. */
export function ProvidersPageClient({ initialProviders, initialPreferences }: Props) {
  const { t } = useI18n();
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
      toast.error(t("providers.refreshFailed", { message: (err as Error).message }));
    }
  }, [setPreferences, setProviders, t]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-xl font-semibold tracking-tight">{t("providers.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("providers.description")}</p>
        </div>
        {!adding && (
          <Button onClick={() => setAdding(true)} size="sm">
            <Plus /> {t("providers.add")}
          </Button>
        )}
      </div>

      {adding && (
        <AddProviderForm
          onClose={() => setAdding(false)}
          onTestConnection={providerService.test}
          onCreate={async (body) => {
            const created = await providerService.create(body);
            toast.success(t("providers.added", { name: body.name }));
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
          toast.success(t("providers.preferencesSaved"));
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
              <p className="text-sm text-muted-foreground">{t("providers.none")}</p>
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
                toast.success(t("providers.updated"));
                return updated;
              }}
              onDelete={async () => {
                await providerService.remove(p.id);
                toast.success(t("providers.deleted", { name: p.name }));
              }}
              onListModels={() => providerService.listModels(p.id)}
              onDeleteModel={async (model) => {
                await providerService.deleteModel(p.id, model);
                toast.success(t("providers.modelRemoved", { model }));
              }}
              onSaveModelDescription={async (model, description) => {
                await providerService.saveModelDescription(p.id, model, description);
                toast.success(t("providers.descriptionSaved"));
              }}
              onSaveApiKey={async (apiKey) => {
                await providerService.saveApiKey(p.id, apiKey);
                toast.success(t("providers.apiKeySaved"));
              }}
              onClearApiKey={async () => {
                await providerService.clearApiKey(p.id);
                toast.success(t("providers.apiKeyCleared"));
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
  );
}
