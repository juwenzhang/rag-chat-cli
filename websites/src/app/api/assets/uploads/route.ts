import { assetApi } from "@/lib/api";
import type { UploadCreateBody } from "@/lib/api/server/assets";

import { readJson, withAuth } from "../../_bff";

export async function POST(req: Request) {
  const body = await readJson<UploadCreateBody>(req);
  return withAuth((token) => assetApi.createUploadSession(token, body));
}
