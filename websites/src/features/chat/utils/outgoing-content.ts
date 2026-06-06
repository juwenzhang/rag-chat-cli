import type { AssetOut } from "@/lib/api/shared/types";

/**
 * Render the composer's draft (text + uploaded image assets) into the
 * single ``content`` string the backend expects.
 *
 * Each attachment becomes a Markdown image link plus an optional
 * description on the next line, joined with blank lines so the
 * server-side splitter (see ``ATTACHED_IMAGE_RE`` in
 * ``user-message.tsx``) round-trips cleanly.
 */
export function buildOutgoingContent(input: string, assets: AssetOut[]): string {
  const text = input.trim();
  const attachmentText = assets.map(formatImageAttachment).join("\n\n");
  if (!attachmentText) return text;
  return [text || "Please review the attached image.", attachmentText]
    .filter(Boolean)
    .join("\n\n");
}

function formatImageAttachment(asset: AssetOut): string {
  const filename = sanitizeAttachmentLine(asset.filename);
  const description = sanitizeAttachmentLine(asset.description ?? "");
  return `[Attached image: ${filename}](${asset.url})${description ? `\n${description}` : ""}`;
}

function sanitizeAttachmentLine(value: string): string {
  return value.replace(/[\r\n\]]+/g, " ").trim();
}
