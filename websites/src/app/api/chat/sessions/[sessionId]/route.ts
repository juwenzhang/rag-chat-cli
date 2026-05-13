import { chatApi } from "@/lib/api";
import type { UpdateSessionBody } from "@/lib/api/chat";

import { readJson, withAuth } from "../../../_bff";

export async function PATCH(
  req: Request,
  ctx: { params: Promise<{ sessionId: string }> }
) {
  const { sessionId } = await ctx.params;
  const body = await readJson<UpdateSessionBody>(req);
  return withAuth((token) => chatApi.updateSession(token, sessionId, body));
}

export async function DELETE(
  _req: Request,
  ctx: { params: Promise<{ sessionId: string }> }
) {
  const { sessionId } = await ctx.params;
  return withAuth(async (token) => {
    await chatApi.deleteSession(token, sessionId);
    return { ok: true };
  });
}
