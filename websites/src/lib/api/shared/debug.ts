const SENSITIVE_KEYS = [
  "authorization",
  "api_key",
  "apikey",
  "password",
  "token",
  "access_token",
  "refresh_token",
  "cookie",
  "set-cookie",
];

export interface ApiDebugMeta {
  requestId?: string;
  method?: string;
  path?: string;
  status?: number;
  durationMs?: number;
  upstreamPath?: string;
  upstreamStatus?: number;
  upstreamDurationMs?: number;
}

export function createRequestId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

export function isApiDebugEnabled(): boolean {
  return process.env.NODE_ENV === "development";
}

export function sanitizeForDebug(value: unknown): unknown {
  if (value == null) return value;
  if (Array.isArray(value)) return value.map(sanitizeForDebug);
  if (typeof value !== "object") return value;

  const out: Record<string, unknown> = {};
  for (const [key, raw] of Object.entries(value as Record<string, unknown>)) {
    const lower = key.toLowerCase();
    out[key] = SENSITIVE_KEYS.some((s) => lower.includes(s))
      ? "[redacted]"
      : sanitizeForDebug(raw);
  }
  return out;
}

export function debugGroup(label: string, payload: Record<string, unknown>): void {
  if (!isApiDebugEnabled()) return;
  const log = console;
  log.groupCollapsed(label);
  for (const [key, value] of Object.entries(payload)) {
    log.log(key, sanitizeForDebug(value));
  }
  log.groupEnd();
}

export function debugServer(label: string, payload: Record<string, unknown>): void {
  if (!isApiDebugEnabled()) return;
  console.info(label, sanitizeForDebug(payload));
}
