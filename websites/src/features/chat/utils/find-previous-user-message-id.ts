import type { UIMessage } from "@/features/chat/components/types";

/**
 * Walk backwards from an assistant message to find the user prompt
 * that triggered it. Returns ``undefined`` for non-assistant inputs
 * or for assistant messages that have no preceding user turn (e.g.
 * a system-seeded greeting).
 */
export function findPreviousUserMessageId(
  messages: UIMessage[],
  index: number
): string | undefined {
  if (messages[index].role !== "assistant") return undefined;
  for (let i = index - 1; i >= 0; i--) {
    if (messages[i].role === "user") return messages[i].id;
  }
  return undefined;
}
