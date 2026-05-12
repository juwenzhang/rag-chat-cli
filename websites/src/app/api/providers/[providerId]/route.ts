import { providerApi } from "@/lib/api";
import type { ProviderUpdateBody } from "@/lib/api/providers";

import { readJson, withAuth } from "../../_bff";

export async function PATCH(
  req: Request,
  ctx: { params: Promise<{ providerId: string }> }
) {
  const { providerId } = await ctx.params;
  const body = await readJson<ProviderUpdateBody>(req);
  return withAuth((token) =>
    providerApi.updateProvider(token, providerId, body)
  );
}

export async function DELETE(
  _req: Request,
  ctx: { params: Promise<{ providerId: string }> }
) {
  const { providerId } = await ctx.params;
  return withAuth(async (token) => {
    await providerApi.deleteProvider(token, providerId);
    return { ok: true };
  });
}
