import { providerApi } from "@/lib/api";

import { readJson, withAuth } from "../../../../_bff";

export async function POST(
  req: Request,
  ctx: { params: Promise<{ providerId: string }> }
) {
  const { providerId } = await ctx.params;
  const body = await readJson<{ model?: string; description?: string | null }>(
    req
  );
  return withAuth((token) =>
    providerApi.upsertModelMeta(token, providerId, {
      model: body.model ?? "",
      description: body.description ?? null,
    })
  );
}
