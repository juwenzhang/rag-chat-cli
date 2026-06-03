const UUID_RE =
  "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
const API_ASSET_FILE_RE = new RegExp(`^/api/assets/(${UUID_RE})/file$`, "i");
const BACKEND_ASSET_FILE_RE = new RegExp(`^/assets/(${UUID_RE})/file$`, "i");
const LEGACY_MINIO_ASSET_RE = new RegExp(`/assets/${UUID_RE}/(${UUID_RE})\\.webp$`, "i");

export function assetFileUrl(assetId: string): string {
  return `/api/assets/${assetId}/file`;
}

export function normalizeAssetUrl(url: string | null | undefined): string {
  if (!url) return "";
  if (API_ASSET_FILE_RE.test(url)) return url;

  const assetSchemeMatch = /^asset:\/\/([^/?#]+)/i.exec(url);
  if (assetSchemeMatch) return assetFileUrl(assetSchemeMatch[1]);

  const path = pathnameFromUrl(url);
  const backendRouteMatch = BACKEND_ASSET_FILE_RE.exec(path);
  if (backendRouteMatch) return assetFileUrl(backendRouteMatch[1]);

  const legacyMinioMatch = LEGACY_MINIO_ASSET_RE.exec(path);
  if (legacyMinioMatch) return assetFileUrl(legacyMinioMatch[1]);

  return url;
}

function pathnameFromUrl(url: string): string {
  try {
    return new URL(url, "http://local.invalid").pathname;
  } catch {
    return url;
  }
}
