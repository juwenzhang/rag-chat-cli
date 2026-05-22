"use client";

import type { UIMessage } from "../types";

/** User message — right-aligned soft-tinted bubble, no avatar. */
export function UserMessage({ message }: { message: UIMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[92%] rounded-2xl bg-user-bubble px-3.5 py-2.5 text-[14px] leading-7 text-user-bubble-foreground shadow-sm sm:max-w-[85%] sm:px-4 sm:text-[15px]">
        <div className="whitespace-pre-wrap break-words">{message.content}</div>
      </div>
    </div>
  );
}
