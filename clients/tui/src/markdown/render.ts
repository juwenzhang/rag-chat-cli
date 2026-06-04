import {highlight, supportsLanguage} from 'cli-highlight';
import {Marked} from 'marked';
import {markedTerminal} from 'marked-terminal';

import {visibleWidth, wrapToWidth} from '../util/ansi-line';

/**
 * 规则书写原则
 * 实例化出来 instance = new Marked();
 * 然后查看适配内容的 token 解析形式做特定的渲染适配即可：token = instance.lexer(content: MarkdownContent)
 */

/**
 * Markdown → ANSI renderer.
 *
 * Stacks on top of marked + marked-terminal:
 *   1. marked-terminal handles the bulk of the work — bullets, blockquotes,
 *      tables (via cli-table3), reflow, emoji.
 *   2. We override colours via its option hooks (heading / strong / em /
 *      codespan / del / link / href / hr / blockquote).
 *   3. We register a few `renderer` overrides on the marked instance itself
 *      so we can see things marked-terminal hides — `heading` level so H1/H2
 *      get different intensities, fenced `code` so we can prepend a language
 *      tag, and `checkbox` so task lists draw as ☑/☐ instead of "[x]".
 *
 * The renderer is keyed by `width` because marked-terminal bakes the column
 * width into its reflow + table layout — switching panes/window size has to
 * rebuild the instance.
 */

const SGR = {
  reset: '\u001b[0m',
  bold: '\u001b[1m',
  dim: '\u001b[2m',
  italic: '\u001b[3m',
  underline: '\u001b[4m',
  strike: '\u001b[9m',
  cyan: '\u001b[36m',
  brightCyan: '\u001b[96m',
  magenta: '\u001b[35m',
  yellow: '\u001b[33m',
  brightYellow: '\u001b[93m',
  green: '\u001b[32m',
  blue: '\u001b[34m',
  brightBlue: '\u001b[94m',
  gray: '\u001b[90m'
} as const;

const HEADING_STYLE = [
  `${SGR.bold}${SGR.brightCyan}`,
  `${SGR.bold}${SGR.cyan}`,
  `${SGR.bold}${SGR.magenta}`,
  `${SGR.bold}${SGR.yellow}`,
  `${SGR.bold}${SGR.green}`,
  `${SGR.bold}${SGR.gray}`
] as const;

let cachedWidth = -1;
let cached: Marked | null = null;

function buildMarked(width: number): Marked {
  const instance = new Marked();

  // marked-terminal — visual baseline.
  instance.use(
    markedTerminal({
      reflowText: true,
      width,
      tab: 2,
      emoji: true,
      // Colour hooks — keep them sober so the transcript reads well on
      // both dark and light terminals.
      strong: (text: string) => `${SGR.bold}${text}${SGR.reset}`,
      em: (text: string) => `${SGR.italic}${text}${SGR.reset}`,
      del: (text: string) => `${SGR.strike}${SGR.dim}${text}${SGR.reset}`,
      codespan: (text: string) => `${SGR.yellow}${text}${SGR.reset}`,
      // marked-terminal calls `link()` with the merged "text (href)" string.
      // We split the trailing `(...)` back out so we can paint the text and
      // the URL differently — readable label vs. low-contrast URL.
      link: (text: string) => formatLink(text),
      href: (href: string) => href,
      blockquote: (text: string) =>
        text
          .split('\n')
          .map((line) => `${SGR.dim}│${SGR.reset} ${line}`)
          .join('\n'),
      hr: () => `${SGR.dim}${'─'.repeat(Math.max(8, Math.min(width, 60)))}${SGR.reset}`,
      // marked-terminal already exports a `heading` hook but only as one
      // colour; we add level-aware styling via the renderer override below
      // and keep this as a pass-through. Same story for `table` — we render
      // it ourselves so we can lay it out against the real viewport width.
      heading: (text: string) => text,
      firstHeading: (text: string) => text,
      table: (text: string) => text
    }) as unknown as Parameters<Marked['use']>[0]
  );

  // ── Block-level extensions ──────────────────────────────────────────
  // marked v12's `renderer.*` hooks still pass the legacy (text, level)
  // strings, so they're a non-starter for anything that needs the parsed
  // token (heading level, fenced code language, table layout). The
  // extension API receives the original token and also takes precedence
  // over marked-terminal's built-ins, so we wire everything through it.
  instance.use({
    renderer: {
      // checkbox's hook signature has always been (checked: bool) → string,
      // so the renderer-level override is fine here.
      checkbox(this: unknown, checked: boolean): string {
        return checked ? `${SGR.green}☑${SGR.reset} ` : `${SGR.dim}☐${SGR.reset} `;
      }
    },
    extensions: [
      {
        name: 'heading',
        level: 'block',
        renderer(this: unknown, token: unknown): string {
          const h = token as HeadingToken;
          const renderer = this as RendererThis;
          const text = renderer.parser.parseInline(h.tokens);
          const level = h.depth || 1;
          const style = HEADING_STYLE[Math.min(level, HEADING_STYLE.length) - 1] ?? HEADING_STYLE[0];
          const prefix = level === 1 ? '' : `${SGR.dim}${'#'.repeat(level)}${SGR.reset} `;
          return `\n${prefix}${style}${text}${SGR.reset}\n\n`;
        }
      },
      {
        name: 'code',
        level: 'block',
        renderer(this: unknown, token: unknown): string {
          const c = token as CodeToken;
          const highlighted = highlightCode(c.text ?? '', c.lang ?? '');
          const innerWidth = Math.max(8, width - 4);
          const label = c.lang
            ? `${SGR.dim}┌─ ${SGR.brightYellow}${c.lang}${SGR.reset}${SGR.dim} ${'─'.repeat(Math.max(0, innerWidth - c.lang.length - 4))}${SGR.reset}`
            : `${SGR.dim}┌${'─'.repeat(innerWidth)}${SGR.reset}`;
          const body = highlighted
            .split('\n')
            .map((line) => `${SGR.dim}│${SGR.reset} ${line}`)
            .join('\n');
          const footer = `${SGR.dim}└${'─'.repeat(innerWidth)}${SGR.reset}`;
          return `\n${label}\n${body}\n${footer}\n\n`;
        }
      },
      {
        name: 'table',
        level: 'block',
        renderer(this: unknown, token: unknown): string {
          return renderTable(token as TableToken, width, this as RendererThis);
        }
      }
    ]
  });

  return instance;
}

interface HeadingToken {
  type: 'heading';
  depth: number;
  tokens: unknown[];
}
interface CodeToken {
  type: 'code';
  text: string;
  lang?: string;
}

interface TableCell {
  text?: string;
  tokens: unknown[];
}
interface TableToken {
  type: 'table';
  header: TableCell[];
  rows: TableCell[][];
  align: Array<'left' | 'right' | 'center' | null>;
}
interface RendererThis {
  parser: {parseInline: (tokens: unknown[]) => string};
}

/**
 * Lay out a markdown table so it always fits inside the transcript viewport.
 *
 * Why not use marked-terminal's built-in (cli-table3)?
 * cli-table3 sizes each column to the natural content width and only wraps
 * when a per-column `colWidths` is configured. When markdown tables exceed
 * the available terminal width the natural layout overflows the bordered
 * transcript pane — visible in lhx-rag as a column's right border drifting
 * off the screen edge and stranding `│` glyphs in odd places.
 *
 * The replacement here:
 *   1. parses each cell's inline tokens so colour/markup survives;
 *   2. computes the natural visible width for every column;
 *   3. fairly distributes any overflow across the widest columns first so
 *      narrow label columns aren't squashed unnecessarily;
 *   4. wraps each cell to its assigned width with ANSI-aware wrap;
 *   5. draws the table with round borders, padded to a fixed visual width
 *      so the transcript can render the rows verbatim.
 */
function renderTable(token: TableToken, width: number, renderer: RendererThis): string {
  // -4 = border (2) + paddingX 1 each side. Same convention as the code
  // block renderer so blocks line up vertically.
  const tableWidth = Math.max(20, width - 4);
  const cols = token.header.length;
  if (cols === 0) return '';

  const headerCells = token.header.map((cell) =>
    normaliseInline(renderer.parser.parseInline(cell.tokens))
  );
  const bodyRows = token.rows.map((row) =>
    row.map((cell) => normaliseInline(renderer.parser.parseInline(cell.tokens)))
  );

  // ── Column width budgeting ──────────────────────────────────────────
  // Each cell costs `width + 2` chars (1 pad each side). The borders add
  // `cols + 1` vertical separators. We work in "interior" widths (the cell
  // text only) and add the framing back at draw time.
  const minWidth = 4;
  const frameOverhead = cols + 1 + cols * 2; // separators + per-cell padding
  const interiorBudget = Math.max(cols * minWidth, tableWidth - frameOverhead);

  // Natural widths come from the widest line inside each cell.
  const natural = new Array<number>(cols).fill(0);
  for (let i = 0; i < cols; i++) {
    natural[i] = Math.max(natural[i] ?? 0, longestVisibleLine(headerCells[i] ?? ''));
    for (const row of bodyRows) {
      natural[i] = Math.max(natural[i] ?? 0, longestVisibleLine(row[i] ?? ''));
    }
    natural[i] = Math.max(minWidth, natural[i] ?? minWidth);
  }
  const widths = fairShare(natural, interiorBudget, minWidth);

  // ── Helpers for drawing ─────────────────────────────────────────────
  const dim = (s: string) => `${SGR.dim}${s}${SGR.reset}`;
  const renderRow = (cells: string[], opts: {bold?: boolean} = {}): string => {
    const wrapped = cells.map((cell, i) =>
      wrapToWidth(cell, widths[i] ?? minWidth)
    );
    const rowHeight = Math.max(1, ...wrapped.map((w) => w.length));
    const lines: string[] = [];
    for (let line = 0; line < rowHeight; line++) {
      const parts: string[] = [];
      for (let c = 0; c < cols; c++) {
        const w = widths[c] ?? minWidth;
        let text = wrapped[c]?.[line] ?? '';
        if (opts.bold) text = `${SGR.bold}${text}${SGR.reset}`;
        const align = token.align[c] ?? 'left';
        parts.push(` ${padCell(text, w, align)} `);
      }
      lines.push(`${dim('│')}${parts.join(dim('│'))}${dim('│')}`);
    }
    return lines.join('\n');
  };

  const sep = (left: string, mid: string, right: string): string => {
    const segments = widths.map((w) => '─'.repeat(w + 2));
    return dim(`${left}${segments.join(mid)}${right}`);
  };

  const out: string[] = [];
  out.push('');
  out.push(sep('╭', '┬', '╮'));
  out.push(renderRow(headerCells, {bold: true}));
  out.push(sep('├', '┼', '┤'));
  for (let r = 0; r < bodyRows.length; r++) {
    out.push(renderRow(bodyRows[r] ?? []));
    if (r < bodyRows.length - 1) out.push(sep('├', '┼', '┤'));
  }
  out.push(sep('╰', '┴', '╯'));
  out.push('');
  return out.join('\n');
}

/**
 * marked-terminal builds links as "text (href)" and hands the whole string
 * to the `link` hook. We re-split that here so the visible label stays
 * brightBlue + underlined, while the URL drops to dim grey without
 * underline — keeps long URLs out of the way visually but still readable.
 *
 * If the string doesn't match the expected shape (e.g. autolinked URLs,
 * angle-bracket links) we just paint the whole thing as a link.
 */
function formatLink(merged: string): string {
  const m = merged.match(/^(.*) \(([^()]+)\)$/);
  if (!m) {
    return `${SGR.brightBlue}${SGR.underline}${merged}${SGR.reset}`;
  }
  const [, label, href] = m;
  return `${SGR.brightBlue}${SGR.underline}${label}${SGR.reset} ${SGR.dim}(${href})${SGR.reset}`;
}

/**
 * Reverse two transforms that marked / marked-terminal apply to inline cell
 * text but that don't make sense in our custom table renderer:
 *
 *   - HTML entity escaping (`&amp;` → `&`, `&lt;` → `<`, …) — marked escapes
 *     these so the original HTML renderer doesn't break the DOM. We render
 *     to ANSI, so the originals are what we want to display.
 *   - marked-terminal's `*#COLON|*` colon-replacer, used to keep `:` from
 *     confusing its built-in table layout. Since we lay tables out ourselves
 *     it just needs to come back as a literal `:`.
 */
const COLON_REPLACER = '*#COLON|*';
const COLON_REPLACER_RE = new RegExp(COLON_REPLACER.replace(/[*|]/g, '\\$&'), 'g');
function normaliseInline(value: string): string {
  return value
    .replace(COLON_REPLACER_RE, ':')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

function longestVisibleLine(text: string): number {
  let max = 0;
  for (const line of text.split('\n')) {
    const w = visibleWidth(line);
    if (w > max) max = w;
  }
  return max;
}

/**
 * Distribute `budget` columns across `natural` so that the sum equals the
 * budget. Columns under `min` get bumped up, the rest are scaled down only
 * if total natural exceeds the budget — wide columns lose width first.
 */
function fairShare(natural: number[], budget: number, min: number): number[] {
  const widths = natural.map((n) => Math.max(min, n));
  let total = widths.reduce((acc, w) => acc + w, 0);
  if (total <= budget) return widths;

  // Shrink the widest columns first until we fit. Each iteration trims one
  // unit from every column wider than `min`, biased toward the widest.
  while (total > budget) {
    const widestIdx = widths.reduce(
      (acc, w, i) => (w > (widths[acc] ?? -1) ? i : acc),
      0
    );
    const current = widths[widestIdx];
    if (current === undefined || current <= min) break;
    widths[widestIdx] = current - 1;
    total -= 1;
  }
  return widths;
}

function padCell(text: string, width: number, align: 'left' | 'right' | 'center'): string {
  const used = visibleWidth(text);
  if (used >= width) return text;
  const pad = ' '.repeat(width - used);
  if (align === 'right') return `${pad}${text}`;
  if (align === 'center') {
    const left = Math.floor(pad.length / 2);
    return `${' '.repeat(left)}${text}${' '.repeat(pad.length - left)}`;
  }
  return `${text}${pad}`;
}

function highlightCode(code: string, lang: string): string {
  const trimmed = code.replace(/\n+$/, '');
  if (!lang) {
    return `${SGR.yellow}${trimmed}${SGR.reset}`;
  }
  try {
    if (supportsLanguage(lang)) {
      return highlight(trimmed, {language: lang, ignoreIllegals: true});
    }
    return highlight(trimmed, {ignoreIllegals: true});
  } catch {
    return `${SGR.yellow}${trimmed}${SGR.reset}`;
  }
}

function getMarked(width: number): Marked {
  if (!cached || width !== cachedWidth) {
    cached = buildMarked(width);
    cachedWidth = width;
  }
  return cached;
}

export function renderMarkdown(source: string, width: number): string {
  if (!source) return '';
  const w = Math.max(20, width);
  let rendered: string;
  try {
    rendered = getMarked(w).parse(source, {async: false}) as string;
  } catch {
    rendered = source;
  }
  return rendered.replace(/\n+$/g, '');
}

// Re-exported so callers (e.g. transcript debug HUD) can sanity-check
// rendered widths without re-implementing the helper.
export {visibleWidth};
