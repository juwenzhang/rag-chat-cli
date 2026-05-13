import { SessionSidebar } from "@/components/chat/session-sidebar";
import { chatApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { getAccessToken, getCurrentUser } from "@/lib/session";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

/**
 * Chat-only sub-shell: this layout renders the conversation list
 * sidebar next to the global rail. /wiki and /bookmarks don't see
 * this — they have their own (or no) module sidebar.
 */
export default async function ChatLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  const token = await getAccessToken();
  if (!token) redirect("/login");

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
    <div className="flex h-full">
      <SessionSidebar user={user} sessions={sessions} />
      <div className="flex-1 overflow-hidden">{children}</div>
    </div>
  );
}
