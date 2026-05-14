import { chatApi } from "@/lib/api";

import { readJson, withAuth } from "../../_bff";

/** List the caller's chat sessions (pinned-first, server-ordered). */
export async function GET() {
  return withAuth((token) => chatApi.listSessions(token));
}

/** Create a new chat session, optionally with a title. */
export async function POST(req: Request) {
  const { title } = await readJson<{ title?: string }>(req);
  return withAuth((token) => chatApi.createSession(token, title));
}
