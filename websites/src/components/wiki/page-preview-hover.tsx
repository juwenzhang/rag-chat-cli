"use client";

import { FileText, Loader2 } from "lucide-react";
import { type ReactNode, useCallback, useRef, useState } from "react";

import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { Markdown } from "@/components/chat/markdown";
import { api } from "@/lib/api/browser";

interface Props {
  /** "wiki-page" or "document" */
  type: "wiki-page" | "document";
  id: string;
  title: string;
  children: ReactNode;
}

/**
 * Wrap a table row (or any element) with this component to show a
 * hover preview card. Content is lazily fetched on first hover and
 * cached for the component lifetime.
 */
export function PagePreviewHover({ type, id, title, children }: Props) {
  const [body, setBody] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const fetchedRef = useRef(false);

  const onOpenChange = useCallback(
    (open: boolean) => {
      if (!open || fetchedRef.current) return;
      fetchedRef.current = true;
      setLoading(true);
      const fetch =
        type === "wiki-page"
          ? api.wikiPages.get(id).then((p) => p.body)
          : api.documents.get(id).then((d) => d.body);
      fetch
        .then((content) => setBody(content))
        .catch(() => setBody("*Failed to load preview*"))
        .finally(() => setLoading(false));
    },
    [type, id]
  );

  return (
    <HoverCard openDelay={400} closeDelay={100} onOpenChange={onOpenChange}>
      <HoverCardTrigger asChild>{children}</HoverCardTrigger>
      <HoverCardContent side="bottom" align="start" sideOffset={4} className="w-80">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <FileText className="size-4 shrink-0 text-primary" />
            <p className="truncate text-sm font-semibold">{title}</p>
          </div>
          <div className="max-h-48 overflow-hidden text-xs text-muted-foreground">
            {loading ? (
              <div className="flex items-center gap-2 py-4">
                <Loader2 className="size-3.5 animate-spin" />
                <span>Loading…</span>
              </div>
            ) : body ? (
              <div className="line-clamp-10">
                <Markdown className="prose-xs **:text-xs **:leading-relaxed">
                  {body.slice(0, 600)}
                </Markdown>
              </div>
            ) : (
              <p className="py-2 italic">No content yet</p>
            )}
          </div>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}
