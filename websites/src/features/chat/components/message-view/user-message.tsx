"use client";

import type { UIMessage } from "../types";

/** User message — right-aligned soft-tinted bubble, no avatar. */
export function UserMessage({ message }: { message: UIMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-2xl bg-user-bubble px-4 py-2.5 text-[15px] leading-7 text-user-bubble-foreground shadow-sm">
        <div className="whitespace-pre-wrap break-words">{message.content}</div>
      </div>
    </div>
  );
}
