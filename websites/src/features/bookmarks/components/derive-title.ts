/**
 * Pull a card-sized title out of the question text. Strips leading
 * markdown punctuation, collapses whitespace, and caps at ~32 chars so it
 * never wraps past two lines in the preview card.
 */
export function deriveTitle(question: string): string {
  const cleaned = question
    .replace(/^[\s#>*\-]+/, "")
    .split(/\n+/)[0]
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return "Untitled question";
  if (cleaned.length <= 32) return cleaned;
  return cleaned.slice(0, 30).trimEnd() + "…";
}
