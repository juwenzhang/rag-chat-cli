import { notFound } from "next/navigation";

import { ChatView } from "@/components/chat/chat-view";
import { chatApi, providerApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { requireAccessToken } from "@/lib/session";

export const dynamic = "force-dynamic";

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

  // Resolve the provider name for historical messages.
  let providerName: string | null = null;
  if (meta?.provider_id) {
    try {
      const providers = await providerApi.listProviders(token);
      const match = providers.find((p) => p.id === meta!.provider_id);
      if (match) providerName = match.name;
    } catch {
      /* non-critical */
    }
  }

  return (
    <ChatView
      sessionId={sessionId}
      initialMessages={messages}
      sessionMeta={meta}
      sessionProviderName={providerName}
    />
  );
}
