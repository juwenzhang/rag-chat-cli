import type { ReactNode } from "react";

/** ``true`` when the fenced-code language should render as a Mermaid diagram. */
export function isMermaidLanguage(language: string | null): boolean {
  return language === "mermaid" || language === "mmd" || language === "marmaid";
}

/** Stable, short hash used as a cache key for rendered Mermaid blocks. */
export function hashString(input: string): string {
  let hash = 0;
  for (let i = 0; i < input.length; i += 1) {
    hash = (hash * 31 + input.charCodeAt(i)) >>> 0;
  }
  return hash.toString(36);
}

/** Pull the ``language-xxx`` class off a code block's first child. */
export function extractLanguage(node: ReactNode): string | null {
  const first = Array.isArray(node) ? node[0] : node;
  if (!first || typeof first !== "object" || !("props" in first)) return null;
  const props = (first as { props: { className?: string } }).props;
  const cls = props?.className || "";
  const match = cls.match(/language-([\w-]+)/);
  return match ? match[1] : null;
}

/** Recursively flatten a React node's text content for slugging / extraction. */
export function extractText(node: ReactNode): string {
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (node && typeof node === "object" && "props" in node) {
    return extractText(
      (node as { props: { children?: ReactNode } }).props.children ?? null
    );
  }
  return "";
}

/**
 * GitHub-style slug from a heading's children. Must stay in lock-step
 * with ``parseToc``'s ``slugify`` (components/wiki/wiki-toc.tsx) so
 * outline anchors match the rendered ids.
 */
export function headingId(children: ReactNode): string {
  const text = extractText(children).trim();
  return (
    text
      .toLowerCase()
      .replace(/[ -⁯⸀-⹿\\'!"#$%&()*+,./:;<=>?@[\]^`{|}~]/g, "")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "") || "section"
  );
}
