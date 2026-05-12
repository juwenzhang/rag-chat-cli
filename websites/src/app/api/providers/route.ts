import { providerApi } from "@/lib/api";
import type { ProviderCreateBody } from "@/lib/api/providers";

import { readJson, withAuth } from "../_bff";

export async function GET() {
  return withAuth((token) => providerApi.listProviders(token));
}

export async function POST(req: Request) {
  const body = await readJson<ProviderCreateBody>(req);
  return withAuth((token) => providerApi.createProvider(token, body));
}
