"use client";

import { normalizeAssetUrl } from "@/lib/assets";

import type { UIMessage } from "../types";

interface AttachedImage {
  filename: string;
  url: string;
  description?: string;
}

const ATTACHED_IMAGE_RE = /\n*\[Attached image: ([^\]]+)\]\(([^)]+)\)(?:\n([^\n]+))?/g;

/** User message — right-aligned soft-tinted bubble, no avatar. */
export function UserMessage({ message }: { message: UIMessage }) {
  const { text, images } = splitAttachedImages(message.content);

  return (
    <div className="flex justify-end">
      <div className="max-w-[92%] rounded-2xl bg-user-bubble px-3.5 py-2.5 text-[14px] leading-7 text-user-bubble-foreground shadow-sm sm:max-w-[85%] sm:px-4 sm:text-[15px]">
        {text ? (
          <div className="whitespace-pre-wrap wrap-break-word">{text}</div>
        ) : images.length > 0 ? (
          <div className="text-sm text-user-bubble-foreground/80">Sent image</div>
        ) : null}
        {images.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {images.map((image) => (
              <a
                key={`${image.filename}-${image.url}`}
                href={image.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block overflow-hidden rounded-xl border border-white/20 bg-black/5"
                title={image.description || image.filename}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- signed user asset URLs are not Next image domains */}
                <img
                  src={image.url}
                  alt={image.filename}
                  className="max-h-56 max-w-64 object-cover"
                />
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function splitAttachedImages(content: string): { text: string; images: AttachedImage[] } {
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
