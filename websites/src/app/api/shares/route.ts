import { shareApi } from "@/lib/api";
import type { CreateShareBody } from "@/lib/api/shares";

import { readJson, withAuth } from "../_bff";

export async function GET() {
  return withAuth((token) => shareApi.listMyShares(token));
}

export async function POST(req: Request) {
  const body = await readJson<CreateShareBody>(req);
  return withAuth((token) => shareApi.createShare(token, body));
}
