/**
 * Centralised palette so we never hard-code colors deep in components. We use
 * Ink's named colors plus a couple of hex accents that resolve to truecolor on
 * modern terminals and degrade gracefully elsewhere.
 */

export const palette = {
  brand: '#7C5CFF',
  accent: 'cyan',
  user: 'cyan',
  assistant: 'magenta',
  system: 'yellow',
  tool: 'blue',
  muted: 'gray',
  border: 'gray',
  borderFocus: 'cyan',
  ok: 'green',
  warn: 'yellow',
  error: 'red',
  text: 'white'
} as const;

export type PaletteKey = keyof typeof palette;
