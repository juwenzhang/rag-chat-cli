"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";

import { useChatStore } from "@/features/chat/stores/chat-store";
import type {
  MessageOut,
  ProviderOut,
  SessionMeta,
  UserPreferenceOut,
} from "@/lib/api/shared/types";
import { useI18n } from "@/lib/i18n/provider";

import { EMPTY_STATE_ICONS } from "../empty-state";
import { ChatToolbar } from "../chat-toolbar";
import { ChatComposer } from "./chat-composer";
import { TranscriptPanel } from "./transcript-panel";

interface Props {
  sessionId: string;
  initialMessages: MessageOut[];
  sessionMeta?: SessionMeta | null;
  sessionProviderName?: string | null;
  initialProviders: ProviderOut[];
  initialPreferences: UserPreferenceOut;
}

export function ChatView({
  sessionId,
  initialMessages,
  sessionMeta,
  sessionProviderName,
  initialProviders,
  initialPreferences,
}: Props) {
  const { t } = useI18n();
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

  const copy = useMemo(
    () => ({
      toolbar: {
        thinking: t("chat.toolbar.thinking"),
      },
      transcript: {
        jumpToLatest: t("chat.jumpToLatest"),
        newTokens: t("chat.newTokens"),
        emptyState: {
          title: t("chat.empty.title", { accent: "" }).trim(),
          titleAccent: t("chat.empty.titleAccent"),
          description: t("chat.empty.description"),
          examples: [
            {
              icon: EMPTY_STATE_ICONS.concept,
              title: t("chat.example.concept.title"),
              prompt: t("chat.example.concept.prompt"),
            },
            {
              icon: EMPTY_STATE_ICONS.refactor,
              title: t("chat.example.refactor.title"),
              prompt: t("chat.example.refactor.prompt"),
            },
            {
              icon: EMPTY_STATE_ICONS.summary,
              title: t("chat.example.summary.title"),
              prompt: t("chat.example.summary.prompt"),
            },
            {
              icon: EMPTY_STATE_ICONS.brainstorm,
              title: t("chat.example.brainstorm.title"),
              prompt: t("chat.example.brainstorm.prompt"),
            },
          ],
        },
      },
      composer: {
        placeholder: t("chat.composer.placeholder"),
        disclaimer: t("chat.composer.disclaimer"),
        stop: t("chat.composer.stop"),
        send: t("chat.composer.send"),
        ragOn: t("chat.composer.ragOn"),
        ragOff: t("chat.composer.ragOff"),
        ragEnabledTip: t("chat.composer.ragEnabledTip"),
        ragDisabledTip: t("chat.composer.ragDisabledTip"),
      },
    }),
    [t]
  );

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
      defaultUseRag: initialPreferences.default_use_rag,
    });
  }, [
    initSession,
    initialMessages,
    sessionId,
    sessionMeta?.model,
    sessionMeta?.provider_id,
    sessionProviderName,
    initialPreferences.default_use_rag,
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
      if (!trimmed || streaming) return false;
      setInput("");
      void send(trimmed, { onTurnStart });
      return true;
    },
    [onTurnStart, send, streaming]
  );

  const jumpToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    stickToBottomRef.current = true;
    setAtBottom(true);
  }, []);

  return (
    <div className="flex h-full flex-col">
      <ChatToolbar
        title={sessionMeta?.title || "New conversation"}
        streaming={streaming}
        thinkingLabel={copy.toolbar.thinking}
      />
      <TranscriptPanel
        messages={messages}
        streaming={streaming}
        scrollRef={scrollRef}
        atBottom={atBottom}
        copy={copy.transcript}
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
        initialProviders={initialProviders}
        initialPreferences={initialPreferences}
        copy={copy.composer}
        onInputChange={setInput}
        onSubmit={submit}
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
  stickToBottomRef: RefObject<boolean>;
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
