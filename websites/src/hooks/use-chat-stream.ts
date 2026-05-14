"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import type { UIMessage } from "@/components/chat/types";
import { api } from "@/lib/api/browser";
import type { MessageOut, StreamEvent } from "@/lib/api/types";
import { ApiError } from "@/lib/api/types";
import { readSse } from "@/lib/sse-client";

/**
 * Rebuild the UI transcript from the server's flat message rows. `tool`
 * rows aren't shown on their own — they're folded back into the
 * `toolResults` of the assistant turn that requested them.
 */
function hydrateMessages(items: MessageOut[]): UIMessage[] {
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

/**
 * Fold one SSE event into the streaming assistant message. Pure — returns
 * a new `UIMessage`; the caller swaps it into the transcript. This is the
 * single reducer that `send` and `regenerate` used to each duplicate.
 */
function applyStreamEvent(message: UIMessage, event: StreamEvent): UIMessage {
  const next: UIMessage = { ...message };
  switch (event.type) {
    case "retrieval":
      next.retrieval = event.data.hits;
      break;
    case "token":
      next.content = (next.content || "") + (event.data.delta || "");
      break;
    case "tool_call":
      // Wire ships `tool_call_id` / `tool_name`; UI consumes `id` / `name`.
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
      break;
    case "error":
      next.streaming = false;
      next.error = event.data.message || event.data.code;
      break;
  }
  return next;
}

interface UseChatStreamOptions {
  sessionId: string;
  /** Server-rendered history; hydrated into the initial transcript. */
  initialMessages: MessageOut[];
  /** Current RAG toggle — read at send time, so toggling mid-session is fine. */
  useRag: boolean;
  /**
   * Fired the moment a turn starts streaming. The chat view uses it to
   * re-pin the scroll-follow flag; the hook itself owns no view state.
   */
  onTurnStart?: () => void;
}

interface UseChatStreamResult {
  messages: UIMessage[];
  streaming: boolean;
  /** Send a new user turn and stream the assistant reply. */
  send: (content: string) => Promise<void>;
  /** Re-stream the trailing assistant turn (or fire the first reply). */
  regenerate: () => Promise<void>;
  /** Abort the in-flight stream, if any. */
  abort: () => void;
}

/**
 * Owns the chat transcript and the SSE streaming lifecycle for one
 * session. Extracted from `ChatView` so the component is left with just
 * rendering + scroll behaviour, and so `send` / `regenerate` share a
 * single stream pipeline instead of duplicating ~140 lines apiece.
 */
export function useChatStream({
  sessionId,
  initialMessages,
  useRag,
  onTurnStart,
}: UseChatStreamOptions): UseChatStreamResult {
  const [messages, setMessages] = useState<UIMessage[]>(() =>
    hydrateMessages(initialMessages)
  );
  const [streaming, setStreaming] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  // Mirror reactive inputs into refs so the stable `send` / `regenerate`
  // callbacks (and the auto-fire effect) always read the latest value
  // without being re-created. Synced in an effect — defined before the
  // auto-fire effect below so the refs are fresh by the time it runs —
  // which keeps the writes out of render.
  const streamingRef = useRef(false);
  const useRagRef = useRef(useRag);
  const onTurnStartRef = useRef(onTurnStart);
  useEffect(() => {
    streamingRef.current = streaming;
    useRagRef.current = useRag;
    onTurnStartRef.current = onTurnStart;
  });

  /**
   * Drive one assistant turn: flip the streaming flag, open the SSE pipe
   * via `open`, and fold each event into the placeholder message. Both
   * entry points (`send`, `regenerate`) funnel through here.
   */
  const runStream = useCallback(
    async (
      open: (signal: AbortSignal) => Promise<Response>,
      placeholderId: string
    ) => {
      setStreaming(true);
      onTurnStartRef.current?.();

      const controller = new AbortController();
      abortRef.current = controller;

      let completed = false;
      let sawError = false;
      try {
        const res = await open(controller.signal);
        for await (const event of readSse(res, controller.signal)) {
          if (event.type === "error") sawError = true;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === placeholderId ? applyStreamEvent(m, event) : m
            )
          );
        }
        completed = true;
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === placeholderId ? { ...m, streaming: false } : m
            )
          );
        } else {
          const msg =
            err instanceof ApiError ? err.message : (err as Error).message;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === placeholderId
                ? { ...m, streaming: false, error: msg }
                : m
            )
          );
          toast.error(msg);
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }

      // The SSE protocol carries no message IDs (see core/chat_service.py),
      // so optimistic rows still hold throwaway `crypto.randomUUID()` ids.
      // On a clean run, pull the persisted history and graft the real DB
      // ids onto this turn's trailing user + assistant rows — that's what
      // unlocks Share / Bookmark, which key on real ids. Streamed-only
      // fields (usage / duration / retrieval hits) are left untouched.
      if (completed && !sawError) {
        try {
          const persisted = await api.chat.getMessages(sessionId);
          const realUserId = [...persisted]
            .reverse()
            .find((m) => m.role === "user")?.id;
          const realAssistantId = [...persisted]
            .reverse()
            .find((m) => m.role === "assistant")?.id;
          setMessages((prev) => {
            const next = [...prev];
            for (let i = next.length - 1; i >= 0; i--) {
              if (realAssistantId && next[i].role === "assistant") {
                next[i] = {
                  ...next[i],
                  id: realAssistantId,
                  persisted: true,
                };
                break;
              }
            }
            for (let i = next.length - 1; i >= 0; i--) {
              if (realUserId && next[i].role === "user") {
                next[i] = { ...next[i], id: realUserId, persisted: true };
                break;
              }
            }
            return next;
          });
        } catch {
          // Non-fatal — the optimistic transcript stays usable; the
          // action buttons just won't light up until the next reload.
        }
      }
    },
    [sessionId]
  );

  const send = useCallback(
    async (content: string) => {
      const trimmed = content.trim();
      if (!trimmed || streamingRef.current) return;

      const userMsg: UIMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: trimmed,
      };
      const assistantId = crypto.randomUUID();
      setMessages((prev) => [
        ...prev,
        userMsg,
        { id: assistantId, role: "assistant", content: "", streaming: true },
      ]);

      await runStream(
        (signal) =>
          api.chat.stream(
            {
              session_id: sessionId,
              content: trimmed,
              use_rag: useRagRef.current,
            },
            signal
          ),
        assistantId
      );
    },
    [sessionId, runStream]
  );

  const regenerate = useCallback(async () => {
    if (streamingRef.current) return;

    // Drop a trailing assistant turn (if any) and append a fresh
    // streaming placeholder — in one update so the UI never flickers an
    // "empty tail" state in between.
    const placeholderId = crypto.randomUUID();
    setMessages((prev) => {
      const trimmed =
        prev.length > 0 && prev[prev.length - 1].role === "assistant"
          ? prev.slice(0, -1)
          : prev;
      return [
        ...trimmed,
        { id: placeholderId, role: "assistant", content: "", streaming: true },
      ];
    });

    await runStream(
      (signal) =>
        api.chat.regenerate(
          { session_id: sessionId, use_rag: useRagRef.current },
          signal
        ),
      placeholderId
    );
  }, [sessionId, runStream]);

  // Auto-fire the first reply when the session ends in a *persisted* user
  // message with no assistant turn yet (the wiki "Ask AI" landing flow
  // seeds one and expects us to fill in the answer). Guarded with a ref
  // so it never re-fires across re-renders or after the stream completes.
  const autoFiredRef = useRef(false);
  useEffect(() => {
    if (autoFiredRef.current || streamingRef.current) return;
    const last = messages[messages.length - 1];
    if (!last || last.role !== "user" || !last.persisted) return;
    autoFiredRef.current = true;
    void regenerate();
  }, [messages, regenerate]);

  const abort = useCallback(() => abortRef.current?.abort(), []);

  return { messages, streaming, send, regenerate, abort };
}
