import { assetApi } from "@/lib/api";

import { bffError, withAuth } from "../../../../../_bff";

interface Ctx {
  params: Promise<{ uploadId: string; index: string }>;
}

export async function PUT(req: Request, ctx: Ctx) {
  const { uploadId, index } = await ctx.params;
  const indexNum = Number.parseInt(index, 10);
  if (!Number.isFinite(indexNum) || indexNum < 0) {
    return bffError("BAD_REQUEST", "invalid chunk index", 400);
  }
  // Read the entire chunk into memory once. For our ≤4 MiB chunk size
  // this stays well under any sensible Node/Next request limit.
  const buffer = await req.arrayBuffer();
  if (buffer.byteLength === 0) {
    return bffError("BAD_REQUEST", "empty chunk", 400);
  }
  return withAuth(async (token) => {
    await assetApi.putUploadChunk(token, uploadId, indexNum, buffer);
    return { ok: true };
  });
}
