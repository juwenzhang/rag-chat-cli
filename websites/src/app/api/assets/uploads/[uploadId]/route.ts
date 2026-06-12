import { assetApi } from "@/lib/api";

import { withAuth } from "../../../_bff";

interface Ctx {
  params: Promise<{ uploadId: string }>;
}

export async function DELETE(_req: Request, ctx: Ctx) {
  const { uploadId } = await ctx.params;
  return withAuth(async (token) => {
    await assetApi.deleteUploadSession(token, uploadId);
    return { ok: true };
  });
}
