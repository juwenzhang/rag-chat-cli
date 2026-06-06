"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useScrollFollow } from "@/features/chat/hooks/use-scroll-follow";
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
  const think = useChatStore((state) => state.think);
  const providerId = useChatStore((state) => state.providerId);
  const model = useChatStore((state) => state.model);
  const initSession = useChatStore((state) => state.initSession);
  const setUseRag = useChatStore((state) => state.setUseRag);
  const setThink = useChatStore((state) => state.setThink);
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
        thinkOn: t("chat.composer.thinkOn"),
        thinkOff: t("chat.composer.thinkOff"),
        thinkEnabledTip: t("chat.composer.thinkEnabledTip"),
        thinkDisabledTip: t("chat.composer.thinkDisabledTip"),
      },
    }),
    [t]
  );

  const router = useRouter();

  const onTurnStart = useCallback(() => {
    stickToBottomRef.current = true;
  }, []);

  // First-turn sidebar refresh: the backend generates the session
  // title fire-and-forget *after* the SSE done event, so we wait a
  // short beat to let that DB write land before refetching server
  // data. 1500 ms is enough for a local LLM round-trip; if the title
  // task is still pending the next user-triggered refresh
  // (rename / pin / new session) will cover it. See
  // service/chat/service.py::_maybe_generate_title.
  const onTurnEnd = useCallback(
    ({ isFirstTurn }: { isFirstTurn: boolean }) => {
      if (!isFirstTurn) return;
      window.setTimeout(() => router.refresh(), 1500);
    },
    [router]
  );

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
    void regenerate({ onTurnStart, onTurnEnd });
  }, [messages, onTurnEnd, onTurnStart, regenerate, sessionId, streaming]);

  const submit = useCallback(
    (content: string) => {
      const trimmed = content.trim();
      if (!trimmed || streaming) return false;
      setInput("");
      void send(trimmed, { onTurnStart, onTurnEnd });
      return true;
    },
    [onTurnEnd, onTurnStart, send, streaming]
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
        onRegenerate={() => void regenerate({ onTurnStart, onTurnEnd })}
        onJumpToBottom={jumpToBottom}
      />
      <ChatComposer
        sessionId={sessionId}
        sessionMeta={sessionMeta}
        input={input}
        streaming={streaming}
        useRag={useRag}
        think={think}
        providerId={providerId}
        model={model}
        inputRef={inputRef}
        initialProviders={initialProviders}
        initialPreferences={initialPreferences}
        copy={copy.composer}
        onInputChange={setInput}
        onSubmit={submit}
        onToggleRag={() => setUseRag(!useRag)}
        onToggleThink={() => setThink(think === false ? true : false)}
        onModelChange={setModelSelection}
        onAbort={abort}
      />
    </div>
  );
}
