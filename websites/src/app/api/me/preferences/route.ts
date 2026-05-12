import { providerApi } from "@/lib/api";
import type { UserPreferenceBody } from "@/lib/api/providers";

import { readJson, withAuth } from "../../_bff";

export async function GET() {
  return withAuth((token) => providerApi.getPreferences(token));
}

export async function PUT(req: Request) {
  const body = await readJson<UserPreferenceBody>(req);
  return withAuth((token) => providerApi.updatePreferences(token, body));
}
