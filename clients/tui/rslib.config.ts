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
 */
export default defineConfig({
  source: {
    entry: {index: './src/index.tsx'}
  },
  lib: [
    {
      format: 'esm',
      bundle: true,
      output: {
        distPath: {root: './dist'},
        filename: {js: 'index.mjs'}
      },
      banner: {js: '#!/usr/bin/env node'}
    }
  ],
  output: {
    target: 'node',
    sourceMap: true
  }
});
