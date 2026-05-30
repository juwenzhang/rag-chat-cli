"use client";

import CodeBlockLowlight from "@tiptap/extension-code-block-lowlight";
import Image from "@tiptap/extension-image";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import TaskItem from "@tiptap/extension-task-item";
import TaskList from "@tiptap/extension-task-list";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { ImagePlus, Loader2 } from "lucide-react";
import { all, createLowlight } from "lowlight";
import { useRef, useState, type ComponentProps } from "react";
import { toast } from "sonner";
import { Markdown } from "tiptap-markdown";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/browser";
import type { AssetOut } from "@/lib/api/shared/types";
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

type FileInputChangeEvent = Parameters<
  NonNullable<ComponentProps<"input">["onChange"]>
>[0];
type EditorPasteEvent = Parameters<NonNullable<ComponentProps<"div">["onPaste"]>>[0];
type EditorDropEvent = Parameters<NonNullable<ComponentProps<"div">["onDrop"]>>[0];

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
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [uploadingCount, setUploadingCount] = useState(0);
  const uploading = uploadingCount > 0;

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
      Image.configure({
        inline: false,
        allowBase64: false,
        HTMLAttributes: {
          loading: "lazy",
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

  const uploadImages = async (files: File[]) => {
    if (!editor || readOnly) return;
    const imageFiles = files.filter((file) => file.type.startsWith("image/"));
    if (imageFiles.length === 0) return;

    setUploadingCount((count) => count + imageFiles.length);
    for (const file of imageFiles) {
      try {
        const asset = await api.assets.uploadImage(file);
        insertImage(editor, asset);
      } catch (err) {
        toast.error((err as Error).message || `Failed to upload ${file.name}`);
      } finally {
        setUploadingCount((count) => Math.max(0, count - 1));
      }
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const onPickImage = () => fileInputRef.current?.click();

  const onFileChange = (event: FileInputChangeEvent) => {
    const files = Array.from(event.target.files ?? []);
    if (files.length > 0) void uploadImages(files);
  };

  const onPaste = (event: EditorPasteEvent) => {
    const files = filesFromClipboard(event.clipboardData);
    if (files.length === 0) return;
    event.preventDefault();
    void uploadImages(files);
  };

  const onDrop = (event: EditorDropEvent) => {
    const files = Array.from(event.dataTransfer.files).filter((file) =>
      file.type.startsWith("image/")
    );
    if (files.length === 0) return;
    event.preventDefault();
    void uploadImages(files);
  };

  if (!editor) return null;
  return (
    <div className={cn("relative", className)} onPaste={onPaste} onDrop={onDrop}>
      {!readOnly && (
        <div className="sticky top-0 z-10 mb-3 flex justify-end bg-background/80 py-1 backdrop-blur">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            className="hidden"
            onChange={onFileChange}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 px-2 text-xs"
            disabled={uploading}
            onClick={onPickImage}
          >
            {uploading ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <ImagePlus className="size-3.5" />
            )}
            <span>{uploading ? "Uploading…" : "Image"}</span>
          </Button>
        </div>
      )}
      <EditorContent editor={editor} />
    </div>
  );
}

function filesFromClipboard(data: DataTransfer): File[] {
  return Array.from(data.items)
    .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
    .map((item) => item.getAsFile())
    .filter((file): file is File => Boolean(file));
}

function insertImage(editor: Editor, asset: AssetOut) {
  editor
    .chain()
    .focus()
    .setImage({
      src: asset.url,
      alt: asset.filename,
      title: asset.description ?? undefined,
    })
    .run();
}
