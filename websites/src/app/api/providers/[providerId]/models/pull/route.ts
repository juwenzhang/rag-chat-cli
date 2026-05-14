import { providerApi } from "@/lib/api";

import { bffError, readJson, withAuthStream } from "../../../../_bff";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  req: Request,
  ctx: { params: Promise<{ providerId: string }> }
) {
  const { providerId } = await ctx.params;
  const body = await readJson<{ model?: string }>(req);
  if (!body.model || typeof body.model !== "string") {
    return bffError("MISSING_MODEL", "model is required.", 400);
  }
  const model = body.model;
  return withAuthStream((token) =>
    providerApi.openPullModelStream(token, providerId, { model })
  );
}
