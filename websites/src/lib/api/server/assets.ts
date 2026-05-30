import "server-only";

import { apiFetch } from "@/lib/api/server/client";
import type { AssetOut } from "@/lib/api/shared/types";

export async function uploadImage(token: string, file: File): Promise<AssetOut> {
  const form = new FormData();
  form.set("file", file);
  return apiFetch<AssetOut>("/assets/images", {
    method: "POST",
    token,
    body: form,
  });
}
