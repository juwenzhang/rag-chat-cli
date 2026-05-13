import { shareApi } from "@/lib/api";

import { readJson, withAuth } from "../../../_bff";

export async function POST(req: Request) {
  const body = await readJson<{ token?: string }>(req);
  const shareToken = body.token ?? "";
  return withAuth((token) => shareApi.forkFromShare(token, shareToken));
}
