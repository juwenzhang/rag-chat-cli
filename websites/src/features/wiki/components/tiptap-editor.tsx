"use client";

import CodeBlockLowlight from "@tiptap/extension-code-block-lowlight";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import TaskItem from "@tiptap/extension-task-item";
import TaskList from "@tiptap/extension-task-list";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { all, createLowlight } from "lowlight";
import { useEffect, useRef, type ComponentProps } from "react";
import { toast } from "sonner";
import { Markdown } from "tiptap-markdown";

import {
  UploadAwareImage,
  filesFromClipboard,
  hasPendingUpload,
  insertUploadingImage,
  newUploadId,
  removeUploadingImage,
  replaceUploadingImage,
} from "@/features/wiki/utils/tiptap-helpers";
import { api } from "@/lib/api/browser";
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

type EditorPasteEvent = Parameters<NonNullable<ComponentProps<"div">["onPaste"]>>[0];
type EditorDropEvent = Parameters<NonNullable<ComponentProps<"div">["onDrop"]>>[0];

/**
 * Feishu/Notion-style WYSIWYG markdown editor backed by TipTap +
 * ProseMirror. See the original module doc for design notes.
 *
 * Image upload UX: when the user pastes or drops images we insert a
 * placeholder node immediately (using a local ``blob:`` URL) so the
 * editor never appears frozen, then the bytes upload in the background
 * and the placeholder's ``src`` is rewritten to the final remote URL
 * once the server returns ``AssetOut``. While placeholders exist we
 * suppress ``onChange`` so the parent's draft persistence never sees
 * a transient ``blob:`` reference.
 */
export function TipTapEditor({
  initialMarkdown,
  readOnly = false,
  onChange,
  onReady,
  className,
}: Props) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  // Track every ``URL.createObjectURL`` we hand to ProseMirror so we
  // can release them on unmount; otherwise the browser pins the file
  // bytes for the lifetime of the document.
  const objectUrlsRef = useRef<Set<string>>(new Set());

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
      UploadAwareImage.configure({
        inline: false,
        // ``blob:`` URLs are not base64, so leaving this off is fine —
        // the placeholder srcs are object URLs not data URIs.
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
      // While any placeholder is still pending we deliberately skip
      // emitting markdown: the parent persists ``onChange`` output as
      // the page body, and we do NOT want a ``blob:`` URL ending up
      // in the database. The final replacement triggers another
      // ``onUpdate`` by virtue of the ``setNodeMarkup`` transaction,
      // and that one will pass this guard.
      if (hasPendingUpload(e)) return;
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

  // Release object URLs on unmount. Individual placeholders also
  // release their URL inline once the upload settles; this is the
  // safety net for the "user navigates away mid-upload" case.
  useEffect(() => {
    const urls = objectUrlsRef.current;
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
      urls.clear();
    };
  }, []);

  const uploadOne = async (file: File) => {
    if (!editor || readOnly) return;
    const uploadId = newUploadId();
    const previewUrl = URL.createObjectURL(file);
    objectUrlsRef.current.add(previewUrl);
    insertUploadingImage(editor, {
      uploadId,
      src: previewUrl,
      alt: file.name,
    });

    try {
      const asset = await api.assets.uploadImage(file);
      const replaced = replaceUploadingImage(editor, uploadId, asset);
      if (!replaced) {
        // The user deleted the placeholder while we were uploading;
        // nothing to do. The asset itself is content-hashed on the
        // server so re-uploading the same bytes later is free.
      }
    } catch (err) {
      removeUploadingImage(editor, uploadId);
      toast.error((err as Error).message || `Failed to upload ${file.name}`);
    } finally {
      URL.revokeObjectURL(previewUrl);
      objectUrlsRef.current.delete(previewUrl);
    }
  };

  const uploadImages = async (files: File[]) => {
    if (!editor || readOnly) return;
    const imageFiles = files.filter((file) => file.type.startsWith("image/"));
    if (imageFiles.length === 0) return;
    // Run uploads in parallel — each one inserts its own placeholder
    // synchronously so the doc reflects all drops/pastes immediately.
    await Promise.all(imageFiles.map(uploadOne));
    if (fileInputRef.current) fileInputRef.current.value = "";
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
      <EditorContent editor={editor} />
    </div>
  );
}
