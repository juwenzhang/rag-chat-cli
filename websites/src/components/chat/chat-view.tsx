"use client";

import { ArrowDown, Brain, Send, Square } from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useChatStream } from "@/hooks/use-chat-stream";
import type { MessageOut, SessionMeta } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { ChatToolbar } from "./chat-toolbar";
import { EmptyState } from "./empty-state";
import { MessageView } from "./message-view";
import { ModelSelector } from "./model-selector";

interface Props {
  sessionId: string;
  initialMessages: MessageOut[];
  sessionMeta?: SessionMeta | null;
}

export function ChatView({ sessionId, initialMessages, sessionMeta }: Props) {
  const [input, setInput] = useState("");
  const [useRag, setUseRag] = useState(true);
  const [providerId, setProviderId] = useState<string | null>(
    sessionMeta?.provider_id ?? null
  );
  const [model, setModel] = useState<string | null>(sessionMeta?.model ?? null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  // ── Scroll follow ────────────────────────────────────────────────
  // Auto-scroll the transcript to the bottom *only* while the user is
  // visually pinned to the bottom. The moment they scroll up to read
  // an earlier message, we stop yanking them back down — they regain
  // control. When they scroll back near the bottom (within 80 px) the
  // follow flag re-arms and streaming continues to glue them to the
  // newest tokens.
  //
  // ``stickToBottomRef`` is a ref (not state) because it gets touched
  // many times per second during a stream and we don't want to trigger
  // re-renders for what is purely view-side bookkeeping.
  const stickToBottomRef = useRef(true);
  // Mirror of the ref above as state — used purely to drive the
  // floating "jump to bottom" pill. We don't read it for scroll
  // decisions (that path stays ref-based, no re-renders).
  const [atBottom, setAtBottom] = useState(true);
  const BOTTOM_THRESHOLD = 80;

  const isNearBottom = useCallback((el: HTMLElement) => {
    return el.scrollHeight - el.scrollTop - el.clientHeight < BOTTOM_THRESHOLD;
  }, []);

  // The transcript + SSE streaming lifecycle live in `useChatStream`;
  // this component is left with rendering and scroll behaviour. The
  // `onTurnStart` callback re-pins the follow flag whenever a new turn
  // begins — sending or regenerating always snaps the user back down.
  const { messages, streaming, send, regenerate, abort } = useChatStream({
    sessionId,
    initialMessages,
    useRag,
    onTurnStart: useCallback(() => {
      stickToBottomRef.current = true;
    }, []),
  });

  // Refresh the follow flag whenever the user (or anything else) scrolls
  // the transcript. The scroll handler is passive so it doesn't fight
  // touchpad inertia.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const near = isNearBottom(el);
      stickToBottomRef.current = near;
      // setState is a no-op when the value doesn't change, so this is
      // safe to call on every scroll — React bails out on identical
      // updates and we only re-render on transitions.
      setAtBottom(near);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [isNearBottom]);

  const jumpToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    stickToBottomRef.current = true;
    setAtBottom(true);
  }, []);

  // Follow the bottom only while the flag is armed. Skipping the
  // assignment lets the user's manual scroll position stay frozen as
  // new tokens stream in above their viewport.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (!stickToBottomRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [messages]);

  // Re-focus the composer once a turn finishes streaming, ready for the
  // next message.
  useEffect(() => {
    if (!streaming) {
      const t = setTimeout(() => inputRef.current?.focus(), 50);
      return () => clearTimeout(t);
    }
  }, [streaming]);

  const submit = useCallback(
    (content: string) => {
      const trimmed = content.trim();
      if (!trimmed || streaming) return;
      setInput("");
      void send(trimmed);
    },
    [send, streaming]
  );

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    submit(input);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      submit(input);
    }
  };

  const empty = messages.length === 0;
  const title = sessionMeta?.title || "New conversation";

  return (
    <div className="flex h-full flex-col">
      <ChatToolbar title={title} streaming={streaming} />

      <div className="relative flex-1 overflow-hidden">
        <div ref={scrollRef} className="h-full overflow-y-auto">
          {empty ? (
            <EmptyState onPick={(p) => submit(p)} />
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-8 px-4 py-8 pb-12">
              {messages.map((m, i) => {
                // Walk back to the nearest user message before this assistant
                // turn. Used by the Share / Bookmark actions which key on the
                // (user_message_id, assistant_message_id) pair.
                let prevUserId: string | undefined;
                if (m.role === "assistant") {
                  for (let j = i - 1; j >= 0; j--) {
                    if (messages[j].role === "user") {
                      prevUserId = messages[j].id;
                      break;
                    }
                  }
                }
                // Regenerate only makes sense for the most recent
                // assistant turn — the backend always re-streams the
                // tail, so older assistant rows would just be
                // misleading buttons.
                const isLastAssistant =
                  m.role === "assistant" &&
                  i === messages.length - 1 &&
                  !m.streaming &&
                  m.persisted === true;
                return (
                  <MessageView
                    key={m.id}
                    message={m}
                    prevUserMessageId={prevUserId}
                    onRegenerate={
                      isLastAssistant && !streaming
                        ? () => void regenerate()
                        : undefined
                    }
                  />
                );
              })}
            </div>
          )}
        </div>

        {/* Floating "↓ jump to latest" pill — visible whenever the user
            has scrolled away from the bottom (so they're "detached"
            from the auto-follow). One click re-anchors them and the
            stream resumes pinning. */}
        {!atBottom && !empty && (
          <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={jumpToBottom}
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
        )}
      </div>

      <form
        onSubmit={onSubmit}
        className="border-t border-border bg-background/80 px-4 py-4 backdrop-blur"
      >
        <div className="mx-auto max-w-3xl">
          <div
            className={cn(
              "relative flex flex-col gap-1 rounded-2xl border border-border bg-card p-2 shadow-sm transition-all",
              "focus-within:border-primary/50 focus-within:shadow-md focus-within:shadow-primary/5"
            )}
          >
            <Textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Ask anything…  (Enter to send, Shift+Enter for newline)"
              rows={1}
              className={cn(
                "min-h-[44px] resize-none border-0 bg-transparent px-2 py-2.5 shadow-none focus-visible:ring-0",
                "max-h-[200px]"
              )}
              style={{
                height: "auto",
              }}
              onInput={(e) => {
                const el = e.currentTarget;
                el.style.height = "auto";
                el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
              }}
              disabled={streaming}
            />

            <div className="flex items-center gap-1 border-t border-border/60 pt-1.5">
              <TooltipProvider delayDuration={200}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setUseRag(!useRag)}
                      disabled={streaming}
                      className={cn(
                        "gap-1.5 text-xs font-normal",
                        useRag
                          ? "text-foreground"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                    >
                      <Brain
                        className={cn(
                          "size-3.5",
                          useRag ? "text-primary" : "text-muted-foreground"
                        )}
                      />
                      <span>RAG</span>
                      <Badge
                        variant={useRag ? "success" : "outline"}
                        className="ml-0.5 text-[9px]"
                      >
                        {useRag ? "on" : "off"}
                      </Badge>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    {useRag
                      ? "Retrieval-augmented context is being added to each turn"
                      : "Click to enable retrieval-augmented context"}
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>

              <div className="ml-auto flex items-center gap-1">
                <ModelSelector
                  sessionId={sessionId}
                  initialProviderId={providerId}
                  initialModel={model}
                  disabled={streaming}
                  onChange={({ provider_id, model: m }) => {
                    setProviderId(provider_id);
                    setModel(m);
                  }}
                />
                {streaming ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={abort}
                    className="size-9 shrink-0 rounded-xl"
                    aria-label="Stop"
                  >
                    <Square className="size-4 fill-current" />
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    size="icon"
                    disabled={!input.trim()}
                    className="size-9 shrink-0 rounded-xl"
                    aria-label="Send"
                  >
                    <Send className="size-4" />
                  </Button>
                )}
              </div>
            </div>
          </div>
          <p className="mt-2 text-center text-[11px] text-muted-foreground">
            lhx-rag may produce inaccurate information. Responses are not stored
            unless you save them to your knowledge base.
          </p>
        </div>
      </form>
    </div>
  );
}
