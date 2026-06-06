/**
 * Heuristic check — does ``text`` contain Markdown syntax that should
 * be rendered through the markdown pipeline rather than displayed raw?
 *
 * Looks for fenced blocks, headings, list markers, blockquotes, table
 * rows, links, emphasis, and inline code. Cheap regex; not a full
 * parser.
 */
export function looksLikeMarkdown(text: string): boolean {
  return (
    /(^|\n)\s*(```|#{1,6}\s|[-*+]\s|\d+\.\s|>\s|\|.+\||```mermaid)/i.test(text) ||
    /\[[^\]]+\]\([^)]+\)|[*_]{1,2}[^*_]+[*_]{1,2}|`[^`]+`/.test(text)
  );
}

/** DOM id for an answer source — used by in-message anchor jumps. */
export function sourceDomId(rank: number): string {
  return `answer-source-${rank}`;
}
