import { chatApi } from "@/lib/api";

import { withAuth } from "../../../../_bff";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ messageId: string }> }
) {
  const { messageId } = await ctx.params;
  return withAuth((token) => chatApi.getMessageEvaluation(token, messageId));
}

export async function POST(
  _req: Request,
  ctx: { params: Promise<{ messageId: string }> }
) {
  const { messageId } = await ctx.params;
  return withAuth((token) => chatApi.evaluateMessage(token, messageId));
}
