export function isHttpUrl(value?: string | null): value is string {
  return typeof value === "string" && /^https?:\/\//i.test(value);
}

export function externalLinkHref(url: string): string {
  return `/external-link?target=${encodeURIComponent(url)}`;
}

export function safeExternalTarget(value?: string | null): string | null {
  if (!isHttpUrl(value)) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    return url.toString();
  } catch {
    return null;
  }
}
