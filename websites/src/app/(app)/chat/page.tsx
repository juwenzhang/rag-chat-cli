import { redirect } from "next/navigation";

import { chatApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { requireAccessToken } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * /chat — landing inside the app shell.
 *
 * If the user has previous sessions, drop them into the most recent one.
 * Otherwise mint a fresh session and redirect to it. This keeps the URL
 * meaningful (always `/chat/<id>`) so refresh + bookmarking work.
 */
export default async function ChatIndex() {
  const token = await requireAccessToken();

  let sessions: Awaited<ReturnType<typeof chatApi.listSessions>> = [];
  try {
    sessions = await chatApi.listSessions(token);
  } catch (err) {
    if (!(err instanceof ApiError)) throw err;
  }

  if (sessions.length > 0) {
    redirect(`/chat/${sessions[0].id}`);
  }

  // No sessions — create one.
  try {
    const meta = await chatApi.createSession(token);
    redirect(`/chat/${meta.id}`);
  } catch (err) {
    if (err instanceof ApiError) {
      return (
        <div className="flex h-full items-center justify-center p-8 text-center">
          <div>
            <h2 className="text-lg font-semibold">Backend unreachable</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              {err.message}
            </p>
            <p className="mt-4 text-xs text-muted-foreground">
              Start the API with{" "}
              <code className="rounded bg-muted px-1.5 py-0.5">
                make dev.api
              </code>{" "}
              and refresh.
            </p>
          </div>
        </div>
      );
    }
    throw err;
  }
}
