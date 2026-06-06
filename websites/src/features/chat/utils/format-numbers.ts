/** Compact token counter: ``987 → "987"``, ``1500 → "1.5k"``, ``42000 → "42k"``. */
export function formatTokens(n: number): string {
  if (n < 1000) return String(n);
  return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`;
}

/** Human-readable duration: ``150 → "150ms"``, ``1500 → "1.5s"``, ``75000 → "1m15s"``. */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)}s`;
  const m = Math.floor(s / 60);
  const r = Math.round(s - m * 60);
  return `${m}m${r}s`;
}

/** Compact byte size: ``42 → "42B"``, ``2048 → "2K"``, ``1572864 → "1.5M"``. */
export function formatSize(bytes: number): string {
  if (bytes <= 0) return "";
  const units = ["B", "K", "M", "G", "T"];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(n < 10 ? 1 : 0)}${units[i]}`;
}
