import { normalizeAssetUrl } from "@/lib/assets";

export interface AttachedImage {
  filename: string;
  url: string;
  description?: string;
}

/**
 * Mirror of the composer's ``buildOutgoingContent`` format: lines
 * matching ``[Attached image: <name>](<url>)\n<optional description>``
 * are pulled out and returned alongside the cleaned text body.
 *
 * Keep the regex / shape in lock-step with
 * ``utils/outgoing-content.ts::formatImageAttachment`` — they are the
 * two halves of the same wire format.
 */
const ATTACHED_IMAGE_RE = /\n*\[Attached image: ([^\]]+)\]\(([^)]+)\)(?:\n([^\n]+))?/g;

export function splitAttachedImages(content: string): {
  text: string;
  images: AttachedImage[];
} {
  const images: AttachedImage[] = [];
  const text = content
    .replace(
      ATTACHED_IMAGE_RE,
      (_match, filename: string, url: string, description?: string) => {
        images.push({ filename, url: normalizeAssetUrl(url), description });
        return "\n";
      }
    )
    .trim();
  return { text, images };
}
