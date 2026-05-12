import { providerApi } from "@/lib/api";
import type { ConnectivityTestBody } from "@/lib/api/providers";

import { readJson, withAuth } from "../../_bff";

export async function POST(req: Request) {
  const body = await readJson<ConnectivityTestBody>(req);
  return withAuth((token) => providerApi.testProvider(token, body));
}
