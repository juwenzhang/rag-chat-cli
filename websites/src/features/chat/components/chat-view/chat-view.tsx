"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type MutableRefObject,
  type RefObject,
} from "react";

import { useChatStore } from "@/features/chat/stores/chat-store";
import type { MessageOut, SessionMeta } from "@/lib/api/shared/types";

import { ChatComposer } from "./chat-composer";
import { ChatToolbar } from "../chat-toolbar";
import { TranscriptPanel } from "./transcript-panel";

interface Props {
  sessionId: string;
  initialMessages: MessageOut[];
  sessionMeta?: SessionMeta | null;
  sessionProviderName?: string | null;
}

export function ChatView({ sessionId, initialMessages, sessionMeta, sessionProviderName }: Props) {
  const [input, setInput] = useState("");
  const messages = useChatStore((state) => state.messages);
  const streaming = useChatStore((state) => state.streaming);
  const useRag = useChatStore((state) => state.useRag);
  const providerId = useChatStore((state) => state.providerId);
  const model = useChatStore((state) => state.model);
  const initSession = useChatStore((state) => state.initSession);
  const setUseRag = useChatStore((state) => state.setUseRag);
  const setModelSelection = useChatStore((state) => state.setModelSelection);
  const send = useChatStore((state) => state.send);
  const regenerate = useChatStore((state) => state.regenerate);
  const abort = useChatStore((state) => state.abort);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const stickToBottomRef = useRef(true);
  const [atBottom, setAtBottom] = useState(true);
  const autoFiredSessionRef = useRef<string | null>(null);

  const onTurnStart = useCallback(() => {
    stickToBottomRef.current = true;
  }, []);

  useEffect(() => {
    initSession({
      sessionId,
      initialMessages,
      sessionModel: sessionMeta?.model,
      sessionProvider: sessionProviderName,
      providerId: sessionMeta?.provider_id ?? null,
      model: sessionMeta?.model ?? null,
    });
  }, [
    initSession,
    initialMessages,
    sessionId,
    sessionMeta?.model,
    sessionMeta?.provider_id,
    sessionProviderName,
  ]);

  useScrollFollow({
    scrollRef,
    stickToBottomRef,
    messages,
    setAtBottom,
  });

  useEffect(() => {
    if (!streaming) {
      const timer = window.setTimeout(() => inputRef.current?.focus(), 50);
      return () => window.clearTimeout(timer);
    }
  }, [streaming]);

  useEffect(() => {
    autoFiredSessionRef.current = null;
  }, [sessionId]);

  useEffect(() => {
    if (autoFiredSessionRef.current === sessionId || streaming) return;
    const last = messages[messages.length - 1];
    if (!last || last.role !== "user" || !last.persisted) return;
    autoFiredSessionRef.current = sessionId;
    void regenerate({ onTurnStart });
  }, [messages, onTurnStart, regenerate, sessionId, streaming]);

  const submit = useCallback(
    (content: string) => {
      const trimmed = content.trim();
      if (!trimmed || streaming) return;
      setInput("");
      void send(trimmed, { onTurnStart });
    },
    [onTurnStart, send, streaming]
  );

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submit(input);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.ctrlKey && !event.metaKey) {
      event.preventDefault();
      submit(input);
    }
  };

  const jumpToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    stickToBottomRef.current = true;
    setAtBottom(true);
  }, []);

  return (
    <div className="flex h-full flex-col">
      <ChatToolbar title={sessionMeta?.title || "New conversation"} streaming={streaming} />
      <TranscriptPanel
        messages={messages}
        streaming={streaming}
        scrollRef={scrollRef}
        atBottom={atBottom}
        onPickPrompt={submit}
        onRegenerate={() => void regenerate({ onTurnStart })}
        onJumpToBottom={jumpToBottom}
      />
      <ChatComposer
        sessionId={sessionId}
        sessionMeta={sessionMeta}
        input={input}
        streaming={streaming}
        useRag={useRag}
        providerId={providerId}
        model={model}
        inputRef={inputRef}
        onInputChange={setInput}
        onSubmit={onSubmit}
        onKeyDown={onKeyDown}
        onToggleRag={() => setUseRag(!useRag)}
        onModelChange={setModelSelection}
        onAbort={abort}
      />
    </div>
  );
}

function useScrollFollow({
  scrollRef,
  stickToBottomRef,
  messages,
  setAtBottom,
}: {
  scrollRef: RefObject<HTMLDivElement | null>;
  stickToBottomRef: MutableRefObject<boolean>;
  messages: unknown[];
  setAtBottom: (next: boolean) => void;
}) {
  const isNearBottom = useCallback((el: HTMLElement) => {
    return el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const near = isNearBottom(el);
      stickToBottomRef.current = near;
      setAtBottom(near);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [isNearBottom, scrollRef, setAtBottom, stickToBottomRef]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (!stickToBottomRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, scrollRef, stickToBottomRef]);
}
