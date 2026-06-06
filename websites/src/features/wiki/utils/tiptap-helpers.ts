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
