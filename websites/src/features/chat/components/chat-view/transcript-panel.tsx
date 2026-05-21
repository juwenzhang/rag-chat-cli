"use client";

import { ArrowDown } from "lucide-react";
import type { RefObject } from "react";

import { Button } from "@/components/ui/button";
import type { UIMessage } from "@/features/chat/components/types";
import { cn } from "@/lib/utils";

import { EmptyState } from "../empty-state";
import { MessageView } from "../message-view";

export function TranscriptPanel({
  messages,
  streaming,
  scrollRef,
  atBottom,
  onPickPrompt,
  onRegenerate,
  onJumpToBottom,
}: {
  messages: UIMessage[];
  streaming: boolean;
  scrollRef: RefObject<HTMLDivElement | null>;
  atBottom: boolean;
  onPickPrompt: (prompt: string) => void;
  onRegenerate: () => void;
  onJumpToBottom: () => void;
}) {
  const empty = messages.length === 0;

  return (
    <div className="relative flex-1 overflow-hidden">
      <div ref={scrollRef} className="h-full overflow-y-auto">
        {empty ? (
          <EmptyState onPick={onPickPrompt} />
        ) : (
          <MessageList
            messages={messages}
            streaming={streaming}
            onRegenerate={onRegenerate}
          />
        )}
      </div>
      {!atBottom && !empty && (
        <JumpToBottomButton
          streaming={streaming}
          onJumpToBottom={onJumpToBottom}
        />
      )}
    </div>
  );
}

function MessageList({
  messages,
  streaming,
  onRegenerate,
}: {
  messages: UIMessage[];
  streaming: boolean;
  onRegenerate: () => void;
}) {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-4 py-8 pb-12">
      {messages.map((message, index) => {
        const prevUserId = findPreviousUserMessageId(messages, index);
        const isLastAssistant =
          message.role === "assistant" &&
          index === messages.length - 1 &&
          !message.streaming &&
          message.persisted === true;

        return (
          <MessageView
            key={message.id}
            message={message}
            prevUserMessageId={prevUserId}
            onRegenerate={
              isLastAssistant && !streaming ? onRegenerate : undefined
            }
          />
        );
      })}
    </div>
  );
}

function JumpToBottomButton({
  streaming,
  onJumpToBottom,
}: {
  streaming: boolean;
  onJumpToBottom: () => void;
}) {
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onJumpToBottom}
        aria-label="Jump to latest"
        className={cn(
          "pointer-events-auto h-8 rounded-full px-3 shadow-md backdrop-blur",
          "border-border bg-background/90 text-foreground/80 hover:text-foreground",
          streaming && "border-primary/40 text-primary hover:text-primary"
        )}
      >
        <ArrowDown className="size-3.5" />
        <span className="text-xs">
          {streaming ? "New tokens" : "Jump to latest"}
        </span>
      </Button>
    </div>
  );
}

function findPreviousUserMessageId(
  messages: UIMessage[],
  index: number
): string | undefined {
  if (messages[index].role !== "assistant") return undefined;
  for (let i = index - 1; i >= 0; i--) {
    if (messages[i].role === "user") return messages[i].id;
  }
  return undefined;
}
