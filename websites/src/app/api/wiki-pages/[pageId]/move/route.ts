import { wikiApi } from "@/lib/api";
import type { MovePageBody } from "@/lib/api/wiki";

import { readJson, withAuth } from "../../../_bff";

interface Ctx {
  params: Promise<{ pageId: string }>;
}

export async function POST(req: Request, { params }: Ctx) {
  const { pageId } = await params;
  const body = await readJson<MovePageBody>(req);
  return withAuth((token) => wikiApi.movePage(token, pageId, body));
}
