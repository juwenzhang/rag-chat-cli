import {appendFileSync} from 'node:fs';

import {debugLogPath} from '../config/paths';

const enabled = process.env['DEBUG'] === '1' || process.env['LHX_DEBUG'] === '1';

/**
 * Debug-only logger. The TUI takes over the screen so println noise breaks the
 * rendering — instead we tee into ~/.config/lhx-rag/debug.log when DEBUG=1.
 */
export const logger = {
  enabled,
  debug(message: string, data?: unknown): void {
    if (!enabled) return;
    const stamp = new Date().toISOString();
    const payload = data === undefined ? '' : ` ${safeStringify(data)}`;
    try {
      appendFileSync(debugLogPath(), `[${stamp}] ${message}${payload}\n`, 'utf-8');
    } catch {
      // swallow — debug logs must never crash the UI
    }
  }
};

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
