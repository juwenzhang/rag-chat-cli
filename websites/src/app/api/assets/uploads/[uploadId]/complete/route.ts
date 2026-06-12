import { assetApi } from "@/lib/api";

import { withAuth } from "../../../../_bff";

interface Ctx {
  params: Promise<{ uploadId: string }>;
}

export async function POST(_req: Request, ctx: Ctx) {
  const { uploadId } = await ctx.params;
  return withAuth((token) => assetApi.completeUploadSession(token, uploadId));
}
