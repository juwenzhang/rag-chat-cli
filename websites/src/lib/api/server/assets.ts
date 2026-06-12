import "server-only";

import { assetFileUrl } from "@/lib/assets";
import { apiFetch } from "@/lib/api/server/client";
import { env } from "@/lib/env";
import type { AssetOut } from "@/lib/api/shared/types";

export interface UploadCreateBody {
  filename: string;
  content_type: string;
  total_size: number;
  source_hash?: string | null;
  chunk_size?: number | null;
}

export interface UploadCreateOut {
  status: "ready" | "completed";
  upload_id?: string | null;
  chunk_size?: number | null;
  expected_chunks?: number | null;
  received_chunks?: number[] | null;
  asset?: AssetOut | null;
}

export interface UploadCompleteOut {
  status: "completed";
  asset: AssetOut;
}

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

export async function createUploadSession(
  token: string,
  body: UploadCreateBody
): Promise<UploadCreateOut> {
  const out = await apiFetch<UploadCreateOut>("/assets/uploads", {
    method: "POST",
    token,
    body,
  });
  return out.asset ? { ...out, asset: toBrowserAsset(out.asset) } : out;
}

/**
 * Stream a single chunk's raw bytes straight through to FastAPI without
 * an intermediate JSON or buffering hop. The chunk body is opaque bytes.
 */
export async function putUploadChunk(
  token: string,
  uploadId: string,
  index: number,
  data: ArrayBuffer | Blob
): Promise<void> {
  const url = new URL(
    `/assets/uploads/${encodeURIComponent(uploadId)}/chunks/${index}`,
    env.RAG_API_URL
  );
  const res = await fetch(url, {
    method: "PUT",
    headers: {
      "Content-Type": "application/octet-stream",
      Authorization: `Bearer ${token}`,
    },
    body: data,
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`chunk upload failed: ${res.status} ${text}`);
  }
}

export async function completeUploadSession(
  token: string,
  uploadId: string
): Promise<UploadCompleteOut> {
  const out = await apiFetch<UploadCompleteOut>(
    `/assets/uploads/${encodeURIComponent(uploadId)}/complete`,
    { method: "POST", token }
  );
  return { ...out, asset: toBrowserAsset(out.asset) };
}

export async function deleteUploadSession(
  token: string,
  uploadId: string
): Promise<void> {
  await apiFetch<void>(`/assets/uploads/${encodeURIComponent(uploadId)}`, {
    method: "DELETE",
    token,
  });
}

function toBrowserAsset(asset: AssetOut): AssetOut {
  return {
    ...asset,
    url: assetFileUrl(asset.id),
  };
}
