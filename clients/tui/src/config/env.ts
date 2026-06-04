import {existsSync, readFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

/**
 * Load `.env` from the package root into `process.env` at runtime.
 *
 * Why bother when rslib already injects values via `source.define`? Because
 * we ship two execution paths:
 *
 *   - `pnpm start` → tsx executes `src/index.tsx` directly, with no rslib
 *     bundle and therefore no compile-time replacements.
 *   - `pnpm build` → rslib emits `dist/index.mjs`, where every reference to
 *     `process.env.FOO` has been substituted at build time.
 *
 * This helper is a no-op in the second case (assignments to process.env
 * keys that already exist are skipped) but provides identical config in the
 * first. Existing process-level env vars always win so users can still do
 * `RAG_API_BASE_URL=… pnpm start`.
 */

let loaded = false;

export function loadDotEnv(): void {
  if (loaded) return;
  loaded = true;

  const here = dirname(fileURLToPath(import.meta.url));
  // src/config → src → package root.
  const candidates = [resolve(here, '..', '..', '.env'), resolve(process.cwd(), '.env')];

  for (const path of candidates) {
    if (!existsSync(path)) continue;
    let raw: string;
    try {
      raw = readFileSync(path, 'utf-8');
    } catch {
      continue;
    }
    for (const line of raw.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const idx = trimmed.indexOf('=');
      if (idx < 0) continue;
      const key = trimmed.slice(0, idx).trim();
      if (!key || process.env[key] !== undefined) continue;
      let value = trimmed.slice(idx + 1).trim();
      if (
        (value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }
      process.env[key] = value;
    }
    return;
  }
}
