import {existsSync, readFileSync} from 'node:fs';
import {resolve} from 'node:path';

import {defineConfig} from '@rslib/core';

/**
 * rslib config for lhx-rag.
 *
 * lhx-rag is a Node CLI/TUI app, not a publishable library. We bundle
 * everything (React + Ink + ink-* + marked + cli-highlight + zustand) into a
 * single ESM file under dist/index.mjs and prepend a shebang so the resulting
 * file is directly executable as `lhx-rag`.
 *
 * Why ESM and not CJS? Several deps in the chain — most notably ink@5,
 * marked-terminal, ink-spinner, ink-text-input — are ESM-only and ship with
 * top-level await. Loading those from a CJS bundle blows up at runtime under
 * recent Node versions, so we publish the entire app as ESM.
 *
 * Build-time env injection: any KEY=VALUE in `clients/tui/.env` is exposed
 * to the bundle as `process.env.KEY` via Rspack's DefinePlugin. The dev
 * runtime (tsx) loads the same file from `src/util/env.ts`, so values
 * resolved through `process.env` work in both modes.
 */
function loadDotEnv(): Record<string, string> {
  const path = resolve(__dirname, '.env');
  if (!existsSync(path)) return {};
  const out: Record<string, string> = {};
  for (const raw of readFileSync(path, 'utf-8').split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const idx = line.indexOf('=');
    if (idx < 0) continue;
    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    out[key] = value;
  }
  return out;
}

const dotenv = loadDotEnv();
const define: Record<string, string> = {};
for (const [key, value] of Object.entries(dotenv)) {
  define[`process.env.${key}`] = JSON.stringify(value);
}

export default defineConfig({
  source: {
    entry: {index: './src/index.tsx'},
    define
  },
  // 需要进行压缩
  lib: [
    {
      format: 'cjs',
      bundle: true,
      output: {
        distPath: {root: './dist'},
        filename: {js: 'index.cjs'}
      },
      banner: {js: '#!/usr/bin/env node'},
    },
  ],
  output: {
    target: 'node',
    sourceMap: true,
    minify: true,
  }
});
