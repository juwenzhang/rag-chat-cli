/**
 * Cross-domain number / size / duration formatters.
 *
 * Two byte-size formatters live here on purpose — they target
 * different surfaces:
 *   - ``formatSize`` is *compact* (``"42K"``), suited to dense table
 *     cells and dropdown rows where horizontal space is scarce.
 *   - ``formatBytes`` is *verbose* (``"42 KB"``), suited to dialog /
 *     progress / detail surfaces where readability wins.
 *
 * Don't merge them — picking the wrong style hurts the surface that
 * needs the other.
 */

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

/** Compact byte size for dense surfaces: ``42 → "42B"``, ``2048 → "2K"``, ``1572864 → "1.5M"``. */
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

/** Verbose byte size for detail surfaces: ``42 → "42 B"``, ``2048 → "2.0 KB"``, ``1572864 → "1.5 MB"``. */
export function formatBytes(n: number): string {
  if (n <= 0) return "0";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`;
}
