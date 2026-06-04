/**
 * Human-friendly formatters used throughout the UI. Pure functions so we can
 * unit test them with no Ink runtime.
 */

export function relativeTime(iso: string | undefined | null, now: Date = new Date()): string {
  if (!iso) return '';
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return '';
  const diff = Math.max(0, now.getTime() - ts);
  const sec = Math.floor(diff / 1000);
  if (sec < 5) return 'now';
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day}d ago`;
  return new Date(ts).toLocaleDateString();
}

export function formatDuration(ms: number | undefined | null): string {
  if (ms === undefined || ms === null) return '';
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds - m * 60);
  return `${m}m${s}s`;
}

export function formatTokens(usage?: Record<string, number> | undefined): string {
  if (!usage) return '';
  const total =
    usage['total_tokens'] ??
    (usage['prompt_tokens'] ?? 0) + (usage['completion_tokens'] ?? 0);
  if (!total) return '';
  return `${total} tok`;
}

export function truncate(value: string, max: number): string {
  if (max <= 1) return value.slice(0, max);
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}
