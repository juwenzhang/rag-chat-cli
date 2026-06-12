import Image from "@tiptap/extension-image";
import type { Editor } from "@tiptap/react";

import type { AssetOut } from "@/lib/api/shared/types";

/** Pull image files (and only image files) out of a clipboard event's DataTransfer. */
export function filesFromClipboard(data: DataTransfer): File[] {
  return Array.from(data.items)
    .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
    .map((item) => item.getAsFile())
    .filter((file): file is File => Boolean(file));
}

/** Insert an uploaded asset as an image node into the active TipTap selection. */
export function insertImage(editor: Editor, asset: AssetOut): void {
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

/**
 * TipTap's built-in ``Image`` extension only round-trips ``src``,
 * ``alt`` and ``title``. We need two extra attributes — ``upload-id``
 * and ``uploading`` — so that:
 *   1. We can locate a placeholder node later and swap its ``src``
 *      for the final remote URL.
 *   2. The ``onUpdate`` handler can tell whether the document still
 *      contains in-flight uploads and avoid emitting a draft markdown
 *      that mentions ``blob:`` URLs.
 *
 * Both attributes are rendered as ``data-*`` so they survive the
 * HTML/Markdown round-trip cleanly (and are stripped by the markdown
 * serializer, which only knows about ``src``/``alt``/``title``).
 */
export const UploadAwareImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      uploadId: {
        default: null,
        parseHTML: (el) => (el as HTMLElement).getAttribute("data-upload-id"),
        renderHTML: (attrs) => {
          const v = (attrs as { uploadId?: string | null }).uploadId;
          return v ? { "data-upload-id": v } : {};
        },
      },
      uploading: {
        default: false,
        parseHTML: (el) => (el as HTMLElement).getAttribute("data-uploading") === "1",
        renderHTML: (attrs) => {
          const v = (attrs as { uploading?: boolean }).uploading;
          return v ? { "data-uploading": "1" } : {};
        },
      },
    };
  },
});

/** Stable-ish id generator for the placeholder bookkeeping. */
export function newUploadId(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof (crypto as Crypto).randomUUID === "function"
  ) {
    return (crypto as Crypto).randomUUID();
  }
  return `upl_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Insert a placeholder image at the current selection. The caller is
 * expected to start an upload and later call ``replaceUploadingImage``
 * (on success) or ``removeUploadingImage`` (on failure) with the same
 * ``uploadId``.
 */
export function insertUploadingImage(
  editor: Editor,
  params: { uploadId: string; src: string; alt?: string }
): void {
  editor
    .chain()
    .focus()
    .insertContent({
      type: "image",
      attrs: {
        src: params.src,
        alt: params.alt ?? "",
        uploadId: params.uploadId,
        uploading: true,
      },
    })
    .run();
}

function findUploadingNodePos(editor: Editor, uploadId: string): number | null {
  let foundAt: number | null = null;
  editor.state.doc.descendants((node, pos) => {
    if (foundAt !== null) return false;
    if (node.type.name === "image" && node.attrs.uploadId === uploadId) {
      foundAt = pos;
      return false;
    }
    return true;
  });
  return foundAt;
}

/** Swap a placeholder image's attributes for the real uploaded asset. */
export function replaceUploadingImage(
  editor: Editor,
  uploadId: string,
  asset: AssetOut
): boolean {
  const pos = findUploadingNodePos(editor, uploadId);
  if (pos === null) return false;
  const node = editor.state.doc.nodeAt(pos);
  if (!node) return false;
  editor.view.dispatch(
    editor.state.tr.setNodeMarkup(pos, undefined, {
      ...node.attrs,
      src: asset.url,
      alt: asset.filename,
      title: asset.description ?? null,
      uploadId: null,
      uploading: false,
    })
  );
  return true;
}

/** Drop the placeholder image entirely (typically after an upload error). */
export function removeUploadingImage(editor: Editor, uploadId: string): boolean {
  const pos = findUploadingNodePos(editor, uploadId);
  if (pos === null) return false;
  const node = editor.state.doc.nodeAt(pos);
  if (!node) return false;
  editor.view.dispatch(editor.state.tr.delete(pos, pos + node.nodeSize));
  return true;
}

/** Walk the doc once and report whether any image is still uploading. */
export function hasPendingUpload(editor: Editor): boolean {
  let pending = false;
  editor.state.doc.descendants((node) => {
    if (pending) return false;
    if (node.type.name === "image" && node.attrs.uploading) {
      pending = true;
      return false;
    }
    return true;
  });
  return pending;
}
