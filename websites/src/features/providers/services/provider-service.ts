import { api } from "@/lib/api/browser";
import type {
  ConnectivityTestBody,
  ProviderCreateBody,
  ProviderUpdateBody,
  UserPreferenceBody,
} from "@/lib/api/server/providers";
import type { ModelListItem } from "@/lib/api/shared/types";

export const providerService = {
  loadSettings: async () =>
    Promise.all([api.providers.list(), api.me.getPreferences()] as const),

  create: (body: ProviderCreateBody) => api.providers.create(body),

  test: (body: ConnectivityTestBody) => api.providers.test(body),

  update: (providerId: string, body: ProviderUpdateBody) =>
    api.providers.update(providerId, body),

  remove: (providerId: string) => api.providers.remove(providerId),

  listModels: (providerId: string) => api.providers.listModels(providerId),

  deleteModel: (providerId: string, model: string) =>
    api.providers.deleteModel(providerId, model),

  saveModelDescription: (
    providerId: string,
    model: string,
    description: string | null
  ) => api.providers.upsertModelMeta(providerId, model, description),

  saveApiKey: (providerId: string, apiKey: string) =>
    api.providers.update(providerId, { api_key: apiKey }),

  clearApiKey: (providerId: string) =>
    api.providers.update(providerId, { clear_api_key: true }),

  updatePreferences: (body: UserPreferenceBody) => api.me.updatePreferences(body),

  pullModel: (providerId: string, model: string, signal?: AbortSignal) =>
    api.providers.pullModel(providerId, model, signal),

  listEmbeddingModels: async (providers: Array<{ id: string; name: string; enabled: boolean }>) => {
    const enabled = providers.filter((p) => p.enabled);
    const results = await Promise.all(
      enabled.map(async (p) => {
        const items = await api.providers
          .listModels(p.id)
          .catch(() => [] as ModelListItem[]);
        return {
          providerName: p.name,
          models: items.filter((m) => m.kind === "embedding"),
        };
      })
    );
    return results.filter((g) => g.models.length > 0);
  },
};
