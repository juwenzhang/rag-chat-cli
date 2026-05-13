"use client";

import { ListTree, PanelRightClose, PanelRightOpen } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface TocItem {
  level: 1 | 2 | 3 | 4 | 5 | 6;
  text: string;
  /** stable slug derived from text, used as the anchor id on rendered
   *  headings (we inject these into the rendered preview). */
  id: string;
}

/**
 * Parse the markdown body for ATX-style headings (``# foo``) and
 * fenced-code-block-aware so a ``# inside ```code```` doesn't get
 * misread as a heading. Returns a flat list with ``level`` and a
 * GitHub-style slug for anchoring.
 */
export function parseToc(markdown: string): TocItem[] {
  const out: TocItem[] = [];
  const lines = markdown.split("\n");
  let inFence = false;
  // Slug collisions get a numeric suffix so the DOM ids stay unique.
  const seen = new Map<string, number>();
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.startsWith("```") || line.startsWith("~~~")) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;
    const m = line.match(/^(#{1,6})\s+(.+?)\s*#*$/);
    if (!m) continue;
    const level = m[1].length as 1 | 2 | 3 | 4 | 5 | 6;
    const text = m[2].trim();
    if (!text) continue;
    let base = slugify(text);
    if (!base) base = "section";
    const count = seen.get(base) ?? 0;
    seen.set(base, count + 1);
    const id = count === 0 ? base : `${base}-${count}`;
    out.push({ level, text, id });
  }
  return out;
}

function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[ -⁯⸀-⹿\\'!"#$%&()*+,./:;<=>?@[\]^`{|}~]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

/**
 * TOC sidebar. Sits to the right of the editor, collapsible. Clicks
 * scroll the rendered preview to the matching anchor.
 */
export function WikiToc({
  items,
  onJump,
}: {
  items: TocItem[];
  onJump: (id: string) => void;
}) {
  const [collapsed, setCollapsed] = useState(false);

  if (collapsed) {
    return (
      <aside className="flex w-10 shrink-0 flex-col items-center border-l border-border bg-card/30 py-3">
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => setCollapsed(false)}
          aria-label="Show outline"
        >
          <PanelRightOpen />
        </Button>
      </aside>
    );
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col border-l border-border bg-card/30">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          <ListTree className="size-3.5" />
          Outline
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => setCollapsed(true)}
          aria-label="Hide outline"
        >
          <PanelRightClose />
        </Button>
      </div>
      {items.length === 0 ? (
        <p className="px-4 py-6 text-center text-xs text-muted-foreground/70">
          Headings will appear here as you write.
        </p>
      ) : (
        <nav className="overflow-y-auto p-2">
          <ul className="space-y-0.5">
            {items.map((it) => (
              <li key={it.id}>
                <button
                  type="button"
                  onClick={() => onJump(it.id)}
                  className={cn(
                    "block w-full truncate rounded px-2 py-1 text-left text-xs transition-colors",
                    "text-muted-foreground hover:bg-accent hover:text-foreground",
                    it.level === 1 && "font-semibold text-foreground/90",
                    it.level === 2 && "pl-4",
                    it.level === 3 && "pl-7",
                    it.level >= 4 && "pl-10 text-[11px]"
                  )}
                  title={it.text}
                >
                  {it.text}
                </button>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </aside>
  );
}
