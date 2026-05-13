import { wikiApi } from "@/lib/api";

import { withAuth } from "../../../_bff";

interface Ctx {
  params: Promise<{ pageId: string }>;
}

export async function POST(_req: Request, { params }: Ctx) {
  const { pageId } = await params;
  return withAuth((token) => wikiApi.duplicatePage(token, pageId));
}
