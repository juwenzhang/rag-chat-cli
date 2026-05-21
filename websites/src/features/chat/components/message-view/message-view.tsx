"use client";

import type { UIMessage } from "../types";

import { AssistantMessage } from "./assistant-message";
import { UserMessage } from "./user-message";

interface MessageViewProps {
  message: UIMessage;
  /**
   * Server id of the user message that precedes this turn. Required for
   * Share / Bookmark actions on an assistant message — both endpoints key
   * on the (user_message_id, assistant_message_id) pair.
   */
  prevUserMessageId?: string;
  /**
   * Set on the most recent assistant message when it's safe to
   * regenerate (stream finished, message persisted, no other stream
   * in flight). Triggers the chat view's regenerate pipeline.
   */
  onRegenerate?: () => void;
}

/** Routes a transcript row to the user- or assistant-shaped renderer. */
export function MessageView({
  message,
  prevUserMessageId,
  onRegenerate,
}: MessageViewProps) {
  if (message.role === "user") {
    return <UserMessage message={message} />;
  }
  return (
    <AssistantMessage
      message={message}
      prevUserMessageId={prevUserMessageId}
      onRegenerate={onRegenerate}
    />
  );
}
