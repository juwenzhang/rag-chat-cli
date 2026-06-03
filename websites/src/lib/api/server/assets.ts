import "server-only";

import { assetFileUrl } from "@/lib/assets";
import { apiFetch } from "@/lib/api/server/client";
import type { AssetOut } from "@/lib/api/shared/types";

export async function uploadImage(token: string, file: File): Promise<AssetOut> {
  const form = new FormData();
  form.set("file", file);
  const asset = await apiFetch<AssetOut>("/assets/images", {
    method: "POST",
    token,
    body: form,
  });
  return toBrowserAsset(asset);
}

export async function getImageDownloadUrl(
  token: string,
  assetId: string
): Promise<string> {
  const asset = await apiFetch<AssetOut>(`/assets/${assetId}`, { token });
  return asset.url;
}

function toBrowserAsset(asset: AssetOut): AssetOut {
  return {
    ...asset,
    url: assetFileUrl(asset.id),
  };
}
