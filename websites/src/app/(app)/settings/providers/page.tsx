import { redirect } from "next/navigation";

import { providerApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { getAccessToken } from "@/lib/session";

import { ProvidersPageClient } from "./providers-page-client";

export const dynamic = "force-dynamic";
export const metadata = {
  title: "Providers · lhx-rag",
};

export default async function ProvidersPage() {
  const token = await getAccessToken();
  if (!token) redirect("/api/auth/clear-and-login");

  let providers: Awaited<ReturnType<typeof providerApi.listProviders>> = [];
  let preferences: Awaited<ReturnType<typeof providerApi.getPreferences>> = {
    default_provider_id: null,
    default_model: null,
    default_embedding_model: null,
    default_use_rag: false,
  };
  try {
    [providers, preferences] = await Promise.all([
      providerApi.listProviders(token),
      providerApi.getPreferences(token),
    ]);
  } catch (err) {
    if (err instanceof ApiError) {
      console.warn("providers page bootstrap failed:", err.message);
    } else {
      throw err;
    }
  }

  return (
    <ProvidersPageClient
      initialProviders={providers}
      initialPreferences={preferences}
    />
  );
}
