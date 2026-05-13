"use client";

import CodeBlockLowlight from "@tiptap/extension-code-block-lowlight";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import TaskItem from "@tiptap/extension-task-item";
import TaskList from "@tiptap/extension-task-list";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { all, createLowlight } from "lowlight";
import { Markdown } from "tiptap-markdown";

import { cn } from "@/lib/utils";

interface Props {
  /** Initial markdown body. Only honoured on the very first render of
   *  this editor instance — re-mount via parent ``key`` to swap pages. */
  initialMarkdown: string;
  readOnly?: boolean;
  onChange: (markdown: string) => void;
  /** Optional hook to grab the editor instance, e.g. for toolbar
   *  buttons or programmatic focus. */
  onReady?: (editor: Editor) => void;
  className?: string;
}

const lowlight = createLowlight(all);

/**
 * Feishu/Notion-style WYSIWYG markdown editor backed by TipTap +
 * ProseMirror. Compared with the previous overlay approach:
 *
 *   - The caret is ProseMirror's, so it always sits where the user
 *     clicks — no drift on headings, code blocks or lists.
 *   - Code blocks accept ``Enter`` to escape via TipTap's
 *     ``code-block-lowlight`` defaults (``Shift+Enter`` for hard
 *     break inside, ``ArrowDown`` past the end exits).
 *   - No spurious textarea scrollbar — there's no textarea anymore;
 *     EditorContent is a contenteditable div that grows naturally.
 *   - Input rules from StarterKit cover the Markdown shortcuts the
 *     user expects: ``# ``, ``## ``, ``- ``, ``1. ``, ``[ ]``,
 *     ``> ``, ``` ``` ``` for code, ``**bold**``, ``*italic*``,
 *     ``~~strike~~``, `` `code` ``, ``[link](href)``.
 *
 * I/O is plain markdown: ``initialMarkdown`` is fed in as the source,
 * ``onChange`` emits the markdown each time the user edits, and the
 * surrounding component persists that string into ``wiki_pages.body``.
 */
export function TipTapEditor({
  initialMarkdown,
  readOnly = false,
  onChange,
  onReady,
  className,
}: Props) {
  const editor = useEditor({
    immediatelyRender: false, // avoid hydration mismatch in Next App Router
    extensions: [
      StarterKit.configure({
        // Replace the default code block with the lowlight-flavoured
        // one so syntax highlighting renders inside the editor.
        codeBlock: false,
        // We attach our own Link extension below so the click + paste
        // handlers can be customised.
        link: false,
      }),
      CodeBlockLowlight.configure({ lowlight }),
      Link.configure({
        openOnClick: false,
        autolink: true,
        HTMLAttributes: {
          rel: "noopener noreferrer nofollow",
          target: "_blank",
        },
      }),
      TaskList,
      TaskItem.configure({ nested: true }),
      Placeholder.configure({
        placeholder: "Type / for commands, or just start writing…",
      }),
      Markdown.configure({
        // Round-trip newlines as paragraph separators; tight lists
        // match Feishu/GFM defaults.
        html: false,
        breaks: false,
        linkify: true,
        tightLists: true,
        transformPastedText: true,
        transformCopiedText: true,
      }),
    ],
    content: initialMarkdown || "",
    editable: !readOnly,
    onCreate: ({ editor: e }) => {
      onReady?.(e);
    },
    onUpdate: ({ editor: e }) => {
      // ``getMarkdown`` is added by the tiptap-markdown extension via
      // editor.storage.markdown — TipTap's ``Storage`` type doesn't
      // see plugin-added slots, so we cast through ``unknown``.
      const md = (
        e.storage as unknown as {
          markdown: { getMarkdown: () => string };
        }
      ).markdown.getMarkdown();
      onChange(md);
    },
    editorProps: {
      attributes: {
        // The contenteditable surface picks up these classes. We
        // reuse the existing ``.markdown-body`` styles so the editor
        // and the chat renderer look the same.
        class: cn(
          "markdown-body wiki-tiptap focus:outline-none",
          "prose-headings:scroll-mt-20"
        ),
      },
    },
  });

  if (!editor) return null;
  return <EditorContent editor={editor} className={className} />;
}
