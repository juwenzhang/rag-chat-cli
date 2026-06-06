/**
 * GitHub-style heading slug. Lowercase, strip punctuation / control
 * characters, collapse whitespace runs to single hyphens.
 *
 * Two consumers must stay in lock-step or anchor jumps break:
 *   - ``features/chat/utils/markdown-helpers.ts::headingId`` — emits
 *     id attributes on rendered headings inside <Markdown>.
 *   - ``features/wiki/components/wiki-toc.tsx`` — slugs the TOC
 *     entries that link to those rendered headings.
 *
 * That's why this lives in ``lib/`` and not in either feature.
 */
export function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[ -⁯⸀-⹿\\'!"#$%&()*+,./:;<=>?@[\]^`{|}~]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}
