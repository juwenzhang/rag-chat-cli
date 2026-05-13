import { providerApi } from "@/lib/api";

import { withAuth } from "../../../_bff";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ providerId: string }> }
) {
  const { providerId } = await ctx.params;
  return withAuth((token) => providerApi.listRunningModels(token, providerId));
}
