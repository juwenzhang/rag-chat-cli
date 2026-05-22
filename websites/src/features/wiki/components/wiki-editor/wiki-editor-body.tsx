"use client";

import type { Editor } from "@tiptap/react";

import { cn } from "@/lib/utils";

import { TipTapEditor } from "../tiptap-editor";
import { WikiToc } from "../wiki-toc";
import type { TocItem } from "../wiki-toc";

export function WikiEditorBody({
  title,
  initialMarkdown,
  readOnly,
  tocItems,
  titlePlaceholder,
  onTitleChange,
  onBodyChange,
  onEditorReady,
  onJumpToHeading,
}: {
  title: string;
  initialMarkdown: string;
  readOnly: boolean;
  tocItems: TocItem[];
  titlePlaceholder: string;
  onTitleChange: (next: string) => void;
  onBodyChange: (next: string) => void;
  onEditorReady: (editor: Editor) => void;
  onJumpToHeading: (index: number) => void;
}) {
  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 pb-20 pt-6 sm:px-12 sm:pb-24 sm:pt-12">
          <input
            value={title}
            onChange={(event) => onTitleChange(event.target.value)}
            readOnly={readOnly}
            placeholder={titlePlaceholder}
            className={cn(
              "mb-6 w-full border-0 bg-transparent p-0 outline-none",
              "text-3xl font-bold tracking-tight sm:text-4xl",
              "placeholder:text-muted-foreground/40"
            )}
            aria-label={titlePlaceholder}
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
