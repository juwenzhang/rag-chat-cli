"use client";

import type { Editor } from "@tiptap/react";

import type { TocItem } from "../wiki-toc";
import { TipTapEditor } from "../tiptap-editor";
import { WikiToc } from "../wiki-toc";
import { cn } from "@/lib/utils";

export function WikiEditorBody({
  title,
  initialMarkdown,
  readOnly,
  tocItems,
  onTitleChange,
  onBodyChange,
  onEditorReady,
  onJumpToHeading,
}: {
  title: string;
  initialMarkdown: string;
  readOnly: boolean;
  tocItems: TocItem[];
  onTitleChange: (next: string) => void;
  onBodyChange: (next: string) => void;
  onEditorReady: (editor: Editor) => void;
  onJumpToHeading: (index: number) => void;
}) {
  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-6 pb-24 pt-8 sm:px-12 sm:pt-12">
          <input
            value={title}
            onChange={(event) => onTitleChange(event.target.value)}
            readOnly={readOnly}
            placeholder="Untitled"
            className={cn(
              "mb-6 w-full border-0 bg-transparent p-0 outline-none",
              "text-4xl font-bold tracking-tight",
              "placeholder:text-muted-foreground/40"
            )}
            aria-label="Page title"
          />
          <TipTapEditor
            initialMarkdown={initialMarkdown}
            readOnly={readOnly}
            onChange={onBodyChange}
            onReady={onEditorReady}
          />
        </div>
      </div>
      <WikiToc items={tocItems} onJump={onJumpToHeading} />
    </div>
  );
}
