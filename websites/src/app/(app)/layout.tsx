import { redirect } from "next/navigation";

import { SessionSidebar } from "@/components/chat/session-sidebar";
import { chatApi, providerApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { getAccessToken, getCurrentUser } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function AppLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const user = await getCurrentUser();
  if (!user) redirect("/api/auth/clear-and-login");

  const token = await getAccessToken();
  if (!token) redirect("/api/auth/clear-and-login");

  // Trigger the backend onboarding seed eagerly: the first /providers call
  // for a user with no UserPreference row seeds a starter Ollama provider
  // from env. Done server-side so the chat toolbar's model selector picks
  // up the seeded entry on its very first render (no race with the
  // lazy fetch inside the dropdown).
  try {
    await providerApi.listProviders(token);
  } catch (err) {
    if (!(err instanceof ApiError)) throw err;
    console.warn("provider bootstrap skipped:", err.message);
  }

  let sessions: Awaited<ReturnType<typeof chatApi.listSessions>> = [];
  try {
    sessions = await chatApi.listSessions(token);
  } catch (err) {
    if (err instanceof ApiError) {
      console.warn("listSessions failed:", err.message);
    } else {
      throw err;
    }
  }

  return (
    <div className="flex h-screen w-full overflow-hidden">
      <SessionSidebar user={user} sessions={sessions} />
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
