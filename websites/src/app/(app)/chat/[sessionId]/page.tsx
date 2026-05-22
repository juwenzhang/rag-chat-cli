import { notFound } from "next/navigation";

import { ChatView } from "@/features/chat/components/chat-view";
import { chatApi, providerApi } from "@/lib/api";
import { ApiError } from "@/lib/api/shared/types";
import { requireAccessToken } from "@/lib/auth/session.server";

export const dynamic = "force-dynamic";

const DEFAULT_PREFERENCES: Awaited<ReturnType<typeof providerApi.getPreferences>> = {
  default_provider_id: null,
  default_model: null,
  default_embedding_model: null,
  default_use_rag: false,
};

export default async function ChatSessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  const token = await requireAccessToken();

  let messages: Awaited<ReturnType<typeof chatApi.getMessages>> = [];
  try {
    messages = await chatApi.getMessages(token, sessionId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    if (!(err instanceof ApiError)) throw err;
  }

  let meta: Awaited<ReturnType<typeof chatApi.listSessions>>[number] | null = null;
  try {
    const all = await chatApi.listSessions(token);
    meta = all.find((s) => s.id === sessionId) ?? null;
  } catch {
    /* non-critical */
  }

  let providers: Awaited<ReturnType<typeof providerApi.listProviders>> = [];
  let preferences: Awaited<ReturnType<typeof providerApi.getPreferences>> = DEFAULT_PREFERENCES;
  try {
    [providers, preferences] = await Promise.all([
      providerApi.listProviders(token),
      providerApi.getPreferences(token),
    ]);
  } catch {
    /* non-critical; model selector renders an empty settings link state */
  }

  const providerName = meta?.provider_id
    ? providers.find((provider) => provider.id === meta.provider_id)?.name ?? null
    : null;

  return (
    <ChatView
      sessionId={sessionId}
      initialMessages={messages}
      sessionMeta={meta}
      sessionProviderName={providerName}
      initialProviders={providers}
      initialPreferences={preferences}
    />
  );
}
