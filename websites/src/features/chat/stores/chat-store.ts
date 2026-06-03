"use client";

import { toast } from "sonner";
import { create } from "zustand";

import type { UIMessage } from "@/features/chat/components/types";
import { api } from "@/lib/api/browser";
import type { MessageOut, StreamEvent, ThinkMode } from "@/lib/api/shared/types";
import { ApiError } from "@/lib/api/shared/types";
import { readSse } from "@/lib/sse/client";

interface InitSessionInput {
  sessionId: string;
  initialMessages: MessageOut[];
  sessionModel?: string | null;
  sessionProvider?: string | null;
  providerId?: string | null;
  model?: string | null;
  defaultUseRag?: boolean;
}

interface TurnOptions {
  onTurnStart?: () => void;
}

interface ChatStore {
  sessionId: string | null;
  messages: UIMessage[];
  streaming: boolean;
  abortController: AbortController | null;
  useRag: boolean;
  think: ThinkMode;
  providerId: string | null;
  model: string | null;
  initSession: (input: InitSessionInput) => void;
  setUseRag: (enabled: boolean) => void;
  setThink: (next: ThinkMode) => void;
  setModelSelection: (next: { provider_id: string | null; model: string | null }) => void;
  send: (content: string, options?: TurnOptions) => Promise<void>;
  regenerate: (options?: TurnOptions) => Promise<void>;
  abort: () => void;
}

function hydrateMessages(
  items: MessageOut[],
  sessionModel?: string | null,
  sessionProvider?: string | null
): UIMessage[] {
  const out: UIMessage[] = [];
  for (const m of items) {
    if (m.role === "user") {
      out.push({ id: m.id, role: "user", content: m.content, persisted: true });
    } else if (m.role === "assistant") {
      out.push({
        id: m.id,
        role: "assistant",
        content: m.content,
        toolCalls: m.tool_calls ?? undefined,
        sources: m.sources ?? undefined,
        retrieval: m.sources
          ?.filter((s) => s.source_type === "document" && s.document_id)
          .map((s) => ({
            document_id: s.document_id!,
            chunk_id: s.chunk_id ?? `${s.document_id}-${s.rank}`,
            score: s.score ?? 0,
            content: s.quote ?? "",
            title: s.title,
            source: s.source,
          })),
        model: sessionModel ?? undefined,
        provider: sessionProvider ?? undefined,
        persisted: true,
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

function applyStreamEvent(message: UIMessage, event: StreamEvent): UIMessage {
  const next: UIMessage = { ...message };
  switch (event.type) {
    case "retrieval":
      next.retrieval = event.data.hits;
      break;
    case "token":
      next.content = (next.content || "") + (event.data.delta || "");
      break;
    case "thought":
      if (event.data.text) {
        next.thoughts = [...(next.thoughts || []), event.data.text];
      }
      break;
    case "tool_call":
      next.toolCalls = [
        ...(next.toolCalls || []),
        {
          id: event.data.tool_call_id,
          name: event.data.tool_name,
          arguments: event.data.arguments,
        },
      ];
      break;
    case "tool_result":
      next.toolResults = [
        ...(next.toolResults || []),
        {
          id: event.data.tool_call_id,
          name: event.data.tool_name,
          output: event.data.content,
          error: event.data.is_error ? event.data.content : undefined,
        },
      ];
      break;
    case "done":
      next.streaming = false;
      next.model = event.data.model ?? null;
      next.provider = event.data.provider_name ?? null;
      next.usage = event.data.usage;
      next.durationMs = event.data.duration_ms;
      next.sources = event.data.sources ?? next.sources;
      break;
    case "error":
      next.streaming = false;
      next.error = event.data.message || event.data.code;
      break;
  }
  return next;
}

export const useChatStore = create<ChatStore>((set, get) => {
  const runStream = async (
    sessionId: string,
    open: (signal: AbortSignal) => Promise<Response>,
    placeholderId: string,
    options?: TurnOptions
  ) => {
    const controller = new AbortController();
    set({ streaming: true, abortController: controller });
    options?.onTurnStart?.();

    let completed = false;
    let sawError = false;
    try {
      const res = await open(controller.signal);
      for await (const event of readSse(res, controller.signal)) {
        if (get().sessionId !== sessionId) return;
        if (event.type === "error") sawError = true;
        set((state) => ({
          messages: state.messages.map((m) =>
            m.id === placeholderId ? applyStreamEvent(m, event) : m
          ),
        }));
      }
      completed = true;
    } catch (err) {
      if (get().sessionId !== sessionId) return;
      if ((err as Error).name === "AbortError") {
        set((state) => ({
          messages: state.messages.map((m) =>
            m.id === placeholderId ? { ...m, streaming: false } : m
          ),
        }));
      } else {
        const msg = err instanceof ApiError ? err.message : (err as Error).message;
        set((state) => ({
          messages: state.messages.map((m) =>
            m.id === placeholderId ? { ...m, streaming: false, error: msg } : m
          ),
        }));
        toast.error(msg);
      }
    } finally {
      if (get().sessionId === sessionId) {
        set({ streaming: false, abortController: null });
      }
    }

    if (completed && !sawError && get().sessionId === sessionId) {
      try {
        const persisted = await api.chat.getMessages(sessionId);
        if (get().sessionId !== sessionId) return;
        set((state) => {
          const knownIds = new Set(
            state.messages.filter((m) => m.persisted).map((m) => m.id)
          );
          let newUserId: string | undefined;
          let newAssistantId: string | undefined;

          for (let i = persisted.length - 1; i >= 0; i--) {
            const pm = persisted[i];
            if (!newAssistantId && pm.role === "assistant" && !knownIds.has(pm.id)) {
              newAssistantId = pm.id;
            }
            if (!newUserId && pm.role === "user" && !knownIds.has(pm.id)) {
              newUserId = pm.id;
            }
            if (newUserId && newAssistantId) break;
          }

          const messages = [...state.messages];
          for (let i = messages.length - 1; i >= 0; i--) {
            if (
              newAssistantId &&
              messages[i].role === "assistant" &&
              !messages[i].persisted
            ) {
              messages[i] = { ...messages[i], id: newAssistantId, persisted: true };
              newAssistantId = undefined;
            }
            if (newUserId && messages[i].role === "user" && !messages[i].persisted) {
              messages[i] = { ...messages[i], id: newUserId, persisted: true };
              newUserId = undefined;
            }
            if (!newUserId && !newAssistantId) break;
          }
          return { messages };
        });
      } catch {
        // Non-fatal: streamed transcript remains usable; persisted IDs arrive on next load.
      }
    }
  };

  return {
    sessionId: null,
    messages: [],
    streaming: false,
    abortController: null,
    useRag: true,
    think: true,
    providerId: null,
    model: null,

    initSession: ({
      sessionId,
      initialMessages,
      sessionModel,
      sessionProvider,
      providerId,
      model,
      defaultUseRag,
    }) => {
      const current = get();
      if (current.sessionId === sessionId) {
        set({
          providerId: providerId ?? null,
          model: model ?? null,
          useRag: defaultUseRag ?? current.useRag,
        });
        return;
      }
      current.abortController?.abort();
      set({
        sessionId,
        messages: hydrateMessages(initialMessages, sessionModel, sessionProvider),
        streaming: false,
        abortController: null,
        providerId: providerId ?? null,
        model: model ?? null,
        useRag: defaultUseRag ?? false,
      });
    },

    setUseRag: (enabled) => set({ useRag: enabled }),

    setThink: (next) => set({ think: next }),

    setModelSelection: (next) => set({ providerId: next.provider_id, model: next.model }),

    send: async (content, options) => {
      const state = get();
      const sessionId = state.sessionId;
      const trimmed = content.trim();
      if (!sessionId || !trimmed || state.streaming) return;

      const userMsg: UIMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
      };
      const assistantId = crypto.randomUUID();
      set((prev) => ({
        messages: [
          ...prev.messages,
          userMsg,
          { id: assistantId, role: "assistant", content: "", streaming: true },
        ],
      }));

      await runStream(
        sessionId,
        (signal) =>
          api.chat.stream(
            {
              session_id: sessionId,
              content: trimmed,
              use_rag: get().useRag,
              think: get().think,
            },
            signal
          ),
        assistantId,
        options
      );
    },

    regenerate: async (options) => {
      const state = get();
      const sessionId = state.sessionId;
      if (!sessionId || state.streaming) return;

      const placeholderId = crypto.randomUUID();
      set((prev) => {
        const trimmed =
          prev.messages.length > 0 &&
          prev.messages[prev.messages.length - 1].role === "assistant"
            ? prev.messages.slice(0, -1)
            : prev.messages;
        return {
          messages: [
            ...trimmed,
            { id: placeholderId, role: "assistant", content: "", streaming: true },
          ],
        };
      });

      await runStream(
        sessionId,
        (signal) =>
          api.chat.regenerate(
            { session_id: sessionId, use_rag: get().useRag, think: get().think },
            signal
          ),
        placeholderId,
        options
      );
    },

    abort: () => get().abortController?.abort(),
  };
});
