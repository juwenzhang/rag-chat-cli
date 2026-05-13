import "server-only";

import { apiFetch, apiStream } from "@/lib/api/client";
import type {
  ConnectivityTestOut,
  ModelListItem,
  ProviderOut,
  UserPreferenceOut,
} from "@/lib/api/types";

export interface ProviderCreateBody {
  name: string;
  type: "ollama" | "openai";
  base_url: string;
  api_key?: string | null;
  is_default?: boolean;
  test_connectivity?: boolean;
}

export interface ProviderUpdateBody {
  name?: string;
  base_url?: string;
  api_key?: string | null;
  clear_api_key?: boolean;
  is_default?: boolean;
  enabled?: boolean;
}

export interface ConnectivityTestBody {
  type: "ollama" | "openai";
  base_url: string;
  api_key?: string | null;
}

export interface UserPreferenceBody {
  default_provider_id?: string | null;
  default_model?: string | null;
  default_embedding_model?: string | null;
  default_use_rag?: boolean;
  clear_default_provider?: boolean;
  clear_default_model?: boolean;
  clear_default_embedding_model?: boolean;
}

export async function listProviders(token: string): Promise<ProviderOut[]> {
  return apiFetch<ProviderOut[]>("/providers", { token });
}

export async function createProvider(
  token: string,
  body: ProviderCreateBody
): Promise<ProviderOut> {
  return apiFetch<ProviderOut>("/providers", {
    method: "POST",
    token,
    body,
  });
}

export async function updateProvider(
  token: string,
  id: string,
  body: ProviderUpdateBody
): Promise<ProviderOut> {
  return apiFetch<ProviderOut>(`/providers/${id}`, {
    method: "PATCH",
    token,
    body,
  });
}

export async function deleteProvider(
  token: string,
  id: string
): Promise<void> {
  await apiFetch(`/providers/${id}`, { method: "DELETE", token });
}

export async function listProviderModels(
  token: string,
  id: string
): Promise<ModelListItem[]> {
  return apiFetch<ModelListItem[]>(`/providers/${id}/models`, { token });
}

/** Open the SSE pull stream from FastAPI — Response is forwarded verbatim. */
export async function openPullModelStream(
  token: string,
  id: string,
  body: { model: string }
): Promise<Response> {
  return apiStream(`/providers/${id}/models/pull`, {
    method: "POST",
    token,
    body,
  });
}

export async function deleteProviderModel(
  token: string,
  id: string,
  model: string
): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/providers/${id}/models/delete`, {
    method: "POST",
    token,
    body: { model },
  });
}

export async function upsertModelMeta(
  token: string,
  id: string,
  body: { model: string; description: string | null }
): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/providers/${id}/models/meta`, {
    method: "POST",
    token,
    body,
  });
}

export async function showProviderModel(
  token: string,
  id: string,
  model: string
): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(`/providers/${id}/models/show`, {
    method: "POST",
    token,
    body: { model },
  });
}

export interface RunningModel {
  name: string;
  size?: number;
  size_vram?: number;
  digest?: string;
  expires_at?: string;
}

export async function listRunningModels(
  token: string,
  id: string
): Promise<RunningModel[]> {
  return apiFetch<RunningModel[]>(`/providers/${id}/ps`, { token });
}

export async function testProvider(
  token: string,
  body: ConnectivityTestBody
): Promise<ConnectivityTestOut> {
  return apiFetch<ConnectivityTestOut>("/providers/test", {
    method: "POST",
    token,
    body,
  });
}

export async function getPreferences(
  token: string
): Promise<UserPreferenceOut> {
  return apiFetch<UserPreferenceOut>("/me/preferences", { token });
}

export async function updatePreferences(
  token: string,
  body: UserPreferenceBody
): Promise<UserPreferenceOut> {
  return apiFetch<UserPreferenceOut>("/me/preferences", {
    method: "PUT",
    token,
    body,
  });
}
