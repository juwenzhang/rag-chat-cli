import stripAnsi from 'strip-ansi';
import stringWidth from 'string-width';

/**
 * ANSI-aware line helpers.
 *
 * Ink's flexbox lays out children by their *visual* width (string-width), but
 * we generate ANSI-coloured strings that include escape sequences. To keep
 * the viewport math truthful we need utilities that can measure and truncate
 * preserving SGR codes.
 */

const SGR_RESET = '\u001b[0m';
const SGR_RE = /\u001b\[[0-9;]*m/g;

export function visibleWidth(line: string): number {
  return stringWidth(stripAnsi(line));
}

/**
 * Truncate to at most `max` visual columns, preserving the surrounding ANSI
 * state. Always appends an SGR reset so the next line never inherits colour.
 */
export function truncateToWidth(line: string, max: number): string {
  if (max <= 0) return '';
  if (visibleWidth(line) <= max) return line;

  let result = '';
  let used = 0;
  let i = 0;
  while (i < line.length) {
    const match = SGR_RE.exec(line);
    SGR_RE.lastIndex = i;
    const next = SGR_RE.exec(line);
    if (next && next.index === i) {
      result += next[0];
      i = next.index + next[0].length;
      SGR_RE.lastIndex = i;
      continue;
    }
    const ch = line[i] ?? '';
    const w = stringWidth(ch);
    if (used + w > max) break;
    result += ch;
    used += w;
    i += 1;
  }
  return `${result}${SGR_RESET}`;
}

/**
 * Pad / truncate so the resulting visual width is exactly `width`. Useful when
 * we render to a fixed grid and want every transcript row to fully overwrite
 * the previous frame.
 */
export function fitToWidth(line: string, width: number): string {
  if (width <= 0) return '';
  const truncated = truncateToWidth(line, width);
  const used = visibleWidth(truncated);
  if (used >= width) return truncated;
  return `${truncated}${' '.repeat(width - used)}`;
}

/**
 * ANSI-aware hard wrap. Walks the source byte by byte, keeping SGR sequences
 * attached to the character that follows them, so colour state never leaks
 * across the wrap boundary. Used by the markdown table renderer to fit each
 * cell into a fixed column width.
 */
export function wrapToWidth(value: string, width: number): string[] {
  if (width <= 0) return [''];
  const out: string[] = [];
  let buffer = '';
  let used = 0;
  let i = 0;
  while (i < value.length) {
    SGR_RE.lastIndex = i;
    const next = SGR_RE.exec(value);
    if (next && next.index === i) {
      buffer += next[0];
      i = next.index + next[0].length;
      continue;
    }
    const ch = value[i] ?? '';
    if (ch === '\n') {
      out.push(`${buffer}${SGR_RESET}`);
      buffer = '';
      used = 0;
      i += 1;
      continue;
    }
    const w = stringWidth(ch);
    if (used + w > width) {
      out.push(`${buffer}${SGR_RESET}`);
      buffer = ch;
      used = w;
    } else {
      buffer += ch;
      used += w;
    }
    i += 1;
  }
  if (buffer.length > 0 || out.length === 0) out.push(`${buffer}${SGR_RESET}`);
  return out;
}
