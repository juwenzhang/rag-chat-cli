import { providerApi } from "@/lib/api";

import { readJson, withAuth } from "../../../../_bff";

export async function POST(
  req: Request,
  ctx: { params: Promise<{ providerId: string }> }
) {
  const { providerId } = await ctx.params;
  const body = await readJson<{ model?: string }>(req);
  return withAuth((token) =>
    providerApi.showProviderModel(token, providerId, body.model ?? "")
  );
}
