import { chatApi } from "@/lib/api";

import { withAuth } from "../../../../_bff";

/** Full message history for a session. */
export async function GET(
  _req: Request,
  ctx: { params: Promise<{ sessionId: string }> }
) {
  const { sessionId } = await ctx.params;
  return withAuth((token) => chatApi.getMessages(token, sessionId));
}
