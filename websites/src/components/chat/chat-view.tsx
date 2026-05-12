"use client";

import { Send, Square } from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import type { MessageOut, SessionMeta } from "@/lib/api/types";
import { readSse } from "@/lib/sse-client";
import { cn } from "@/lib/utils";

import { ChatToolbar } from "./chat-toolbar";
import { EmptyState } from "./empty-state";
import { MessageView } from "./message-view";
import type { UIMessage } from "./types";

interface Props {
  sessionId: string;
  initialMessages: MessageOut[];
  sessionMeta?: SessionMeta | null;
}

function hydrateMessages(items: MessageOut[]): UIMessage[] {
  const out: UIMessage[] = [];
  for (const m of items) {
    if (m.role === "user") {
      out.push({ id: m.id, role: "user", content: m.content });
    } else if (m.role === "assistant") {
      out.push({
        id: m.id,
        role: "assistant",
        content: m.content,
        toolCalls: m.tool_calls ?? undefined,
      });
    } else if (m.role === "tool") {
      for (let i = out.length - 1; i >= 0; i--) {
        if (out[i].role === "assistant") {
          out[i].toolResults = out[i].toolResults ?? [];
          out[i].toolResults!.push({
            id: m.tool_call_id ?? m.id,
            name: "tool",
            output: m.content,
          });
          break;
        }
      }
    }
  }
  return out;
}

export function ChatView({ sessionId, initialMessages, sessionMeta }: Props) {
  const [messages, setMessages] = useState<UIMessage[]>(() =>
    hydrateMessages(initialMessages)
  );
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [useRag, setUseRag] = useState(true);
  const [providerId, setProviderId] = useState<string | null>(
    sessionMeta?.provider_id ?? null
  );
  const [model, setModel] = useState<string | null>(sessionMeta?.model ?? null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages]);

  const send = useCallback(
    async (content: string) => {
      const trimmed = content.trim();
      if (!trimmed || streaming) return;

      const userMsg: UIMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
      };
      const assistantMsg: UIMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "",
        streaming: true,
      };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setInput("");
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const res = await fetch("/api/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            content: trimmed,
            use_rag: useRag,
          }),
          signal: controller.signal,
        });

        if (!res.ok) {
          const payload = await res.json().catch(() => ({}));
          const msg =
            (payload as { message?: string }).message || `HTTP ${res.status}`;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id
                ? { ...m, streaming: false, error: msg }
                : m
            )
          );
          toast.error(msg);
          return;
        }

        for await (const event of readSse(res, controller.signal)) {
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== assistantMsg.id) return m;
              const next: UIMessage = { ...m };
              switch (event.type) {
                case "retrieval":
                  next.retrieval = event.data.hits;
                  break;
                case "token":
                  next.content = (next.content || "") + (event.data.delta || "");
                  break;
                case "tool_call":
                  next.toolCalls = [...(next.toolCalls || []), event.data];
                  break;
                case "tool_result":
                  next.toolResults = [...(next.toolResults || []), event.data];
                  break;
                case "done":
                  next.streaming = false;
                  break;
                case "error":
                  next.streaming = false;
                  next.error = event.data.message || event.data.code;
                  break;
              }
              return next;
            })
          );
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id ? { ...m, streaming: false } : m
            )
          );
        } else {
          const msg = (err as Error).message;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id
                ? { ...m, streaming: false, error: msg }
                : m
            )
          );
          toast.error(msg);
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
        // Re-focus input for the next turn
        setTimeout(() => inputRef.current?.focus(), 50);
      }
    },
    [sessionId, streaming, useRag]
  );

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    void send(input);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      void send(input);
    }
  };

  const abort = () => abortRef.current?.abort();

  const empty = messages.length === 0;
  const title = sessionMeta?.title || "New conversation";

  return (
    <div className="flex h-full flex-col">
      <ChatToolbar
        title={title}
        useRag={useRag}
        onToggleRag={setUseRag}
        streaming={streaming}
        sessionId={sessionId}
        providerId={providerId}
        model={model}
        onModelChange={({ provider_id, model: m }) => {
          setProviderId(provider_id);
          setModel(m);
        }}
      />

      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {empty ? (
          <EmptyState onPick={(p) => void send(p)} />
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-8 px-4 py-8 pb-12">
            {messages.map((m) => (
              <MessageView key={m.id} message={m} />
            ))}
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
              "relative flex items-end gap-2 rounded-2xl border border-border bg-card p-2 shadow-sm transition-all",
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

            {streaming ? (
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={abort}
                className="size-10 shrink-0 rounded-xl"
                aria-label="Stop"
              >
                <Square className="fill-current" />
              </Button>
            ) : (
              <Button
                type="submit"
                size="icon"
                disabled={!input.trim()}
                className="size-10 shrink-0 rounded-xl"
                aria-label="Send"
              >
                <Send />
              </Button>
            )}
          </div>
          <p className="mt-2 text-center text-[11px] text-muted-foreground">
            RAG-AI may produce inaccurate information. Responses are not stored
            unless you save them to your knowledge base.
          </p>
        </div>
      </form>
    </div>
  );
}
