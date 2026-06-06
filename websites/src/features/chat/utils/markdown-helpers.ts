import type { ReactNode } from "react";

import { slugify } from "@/lib/slug";

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
 * Heading id used by rendered Markdown — flatten children to text and
 * slug it via the shared ``lib/slug`` so wiki TOC anchors line up.
 */
export function headingId(children: ReactNode): string {
  return slugify(extractText(children).trim()) || "section";
}
