import "server-only";

import { apiFetch } from "@/lib/api/client";
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
  default_use_rag?: boolean;
  clear_default_provider?: boolean;
  clear_default_model?: boolean;
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
