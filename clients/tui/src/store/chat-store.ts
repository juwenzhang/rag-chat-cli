import {create} from 'zustand';

import type {ApiClient} from '../api/client';
import {readSse} from '../api/sse';
import type {
  AnswerSource,
  KnowledgeHit,
  MessageOut,
  StreamEvent,
  ThinkMode,
  ToolCallOut
} from '../api/types';
import {logger} from '../util/logger';

/**
 * Chat domain model. We keep richer state than MessageOut so the transcript
 * can render streaming progress, tool calls, retrieval hits and metadata in
 * one pass without re-fetching after each turn.
 */
export interface UIMessage {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  createdAt: string;
  streaming: boolean;
  thoughts: string[];
  toolCalls: ToolCallOut[];
  toolResults: Array<{id: string; name: string; output: string; error?: string}>;
  retrieval: KnowledgeHit[] | null;
  sources: AnswerSource[] | null;
  usage?: Record<string, number>;
  durationMs?: number;
  model?: string | null;
  provider?: string | null;
  error?: string;
}

interface ChatState {
  messages: UIMessage[];
  /** Map<sessionId, UIMessage[]> so switching sessions is cheap. */
  cache: Record<string, UIMessage[]>;
  loading: boolean;
  streaming: boolean;
  useRag: boolean;
  thinkMode: ThinkMode;
  abortController: AbortController | null;
  error: string | null;

  setUseRag: (value: boolean) => void;
  setThink: (value: ThinkMode) => void;

  loadSession: (api: ApiClient, sessionId: string) => Promise<void>;
  clearLocal: (sessionId: string) => void;
  reset: () => void;

  send: (api: ApiClient, sessionId: string, content: string) => Promise<void>;
  regenerate: (api: ApiClient, sessionId: string) => Promise<void>;
  stop: () => void;
}

const TEMP_PREFIX = 'temp-';

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  cache: {},
  loading: false,
  streaming: false,
  useRag: false,
  thinkMode: false,
  abortController: null,
  error: null,

  setUseRag(value) {
    set({useRag: value});
  },

  setThink(value) {
    set({thinkMode: value});
  },

  async loadSession(api, sessionId) {
    set({loading: true, error: null});
    try {
      const raw = await api.getMessages(sessionId);
      const messages = raw.map(hydrate);
      set((state) => ({
        loading: false,
        messages,
        cache: {...state.cache, [sessionId]: messages}
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'failed to load messages';
      set({loading: false, error: message, messages: []});
    }
  },

  clearLocal(sessionId) {
    set((state) => {
      const next = {...state.cache};
      delete next[sessionId];
      return {cache: next, messages: []};
    });
  },

  reset() {
    get().abortController?.abort();
    set({
      messages: [],
      cache: {},
      streaming: false,
      abortController: null,
      error: null
    });
  },

  async send(api, sessionId, content) {
    if (get().streaming) return;
    const userMessage: UIMessage = {
      id: `${TEMP_PREFIX}user-${Date.now()}`,
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
      streaming: false,
      thoughts: [],
      toolCalls: [],
      toolResults: [],
      retrieval: null,
      sources: null
    };
    const assistant: UIMessage = {
      id: `${TEMP_PREFIX}asst-${Date.now()}`,
      role: 'assistant',
      content: '',
      createdAt: new Date().toISOString(),
      streaming: true,
      thoughts: [],
      toolCalls: [],
      toolResults: [],
      retrieval: null,
      sources: null
    };
    appendMessages([userMessage, assistant], sessionId, set);

    const controller = new AbortController();
    set({streaming: true, abortController: controller, error: null});

    try {
      const response = await api.openChatStream(
        {
          session_id: sessionId,
          content,
          use_rag: get().useRag,
          think: get().thinkMode
        },
        controller.signal
      );
      await consumeStream(response, controller.signal, assistant.id, set, get);
    } catch (error) {
      handleStreamError(error, assistant.id, set, get);
    }
  },

  async regenerate(api, sessionId) {
    if (get().streaming) return;
    const placeholder: UIMessage = {
      id: `${TEMP_PREFIX}asst-${Date.now()}`,
      role: 'assistant',
      content: '',
      createdAt: new Date().toISOString(),
      streaming: true,
      thoughts: [],
      toolCalls: [],
      toolResults: [],
      retrieval: null,
      sources: null
    };
    appendMessages([placeholder], sessionId, set);

    const controller = new AbortController();
    set({streaming: true, abortController: controller, error: null});

    try {
      const response = await api.openRegenerateStream(
        {session_id: sessionId, use_rag: get().useRag, think: get().thinkMode},
        controller.signal
      );
      await consumeStream(response, controller.signal, placeholder.id, set, get);
    } catch (error) {
      handleStreamError(error, placeholder.id, set, get);
    }
  },

  stop() {
    get().abortController?.abort();
  }
}));

/* ── helpers ───────────────────────────────────────────────────────── */

function hydrate(message: MessageOut): UIMessage {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    createdAt: message.created_at,
    streaming: false,
    thoughts: [],
    toolCalls: message.tool_calls ?? [],
    toolResults: [],
    retrieval: null,
    sources: message.sources ?? null
  };
}

function appendMessages(
  toAppend: UIMessage[],
  sessionId: string,
  set: (partial: Partial<ChatState> | ((state: ChatState) => Partial<ChatState>)) => void
): void {
  set((state) => {
    const merged = [...state.messages, ...toAppend];
    return {
      messages: merged,
      cache: {...state.cache, [sessionId]: merged}
    };
  });
}

function applyEvent(message: UIMessage, event: StreamEvent): UIMessage {
  switch (event.type) {
    case 'retrieval':
      return {...message, retrieval: event.data.hits};
    case 'token':
      return {...message, content: message.content + (event.data.delta ?? '')};
    case 'thought':
      if (!event.data.text) return message;
      return {...message, thoughts: [...message.thoughts, event.data.text]};
    case 'tool_call':
      return {
        ...message,
        toolCalls: [
          ...message.toolCalls,
          {id: event.data.tool_call_id, name: event.data.tool_name, arguments: event.data.arguments}
        ]
      };
    case 'tool_result':
      return {
        ...message,
        toolResults: [
          ...message.toolResults,
          {
            id: event.data.tool_call_id,
            name: event.data.tool_name,
            output: event.data.content,
            error: event.data.is_error ? event.data.content : undefined
          }
        ]
      };
    case 'done':
      return {
        ...message,
        streaming: false,
        id: event.data.message_id ?? message.id,
        usage: event.data.usage,
        durationMs: event.data.duration_ms,
        sources: event.data.sources ?? message.sources,
        model: event.data.model ?? null,
        provider: event.data.provider_name ?? null
      };
    case 'error':
      return {...message, streaming: false, error: event.data.message || event.data.code};
    default:
      return message;
  }
}

async function consumeStream(
  response: Response,
  signal: AbortSignal,
  messageId: string,
  set: (partial: Partial<ChatState> | ((state: ChatState) => Partial<ChatState>)) => void,
  get: () => ChatState
): Promise<void> {
  try {
    for await (const event of readSse(response, signal)) {
      logger.debug('stream event', event);
      const previous = get().messages.find((m) => m.id === messageId);
      const updated = previous ? applyEvent(previous, event) : null;
      if (!updated) continue;
      const newId = updated.id;
      set((state) => {
        const messages = state.messages.map((m) => (m.id === messageId ? updated : m));
        const sessionEntries = Object.entries(state.cache).map(([sid, list]) => {
          if (!list.some((m) => m.id === messageId)) return [sid, list] as const;
          return [sid, list.map((m) => (m.id === messageId ? updated : m))] as const;
        });
        return {
          messages,
          cache: Object.fromEntries(sessionEntries)
        };
      });
      // The "done" event may rename the temp id to a real message id. Update
      // our local cursor so subsequent events keep targeting the right row.
      if (newId !== messageId) {
        messageId = newId;
      }
    }
  } finally {
    set({streaming: false, abortController: null});
  }
}

function handleStreamError(
  error: unknown,
  messageId: string,
  set: (partial: Partial<ChatState> | ((state: ChatState) => Partial<ChatState>)) => void,
  get: () => ChatState
): void {
  const aborted = error instanceof Error && error.name === 'AbortError';
  const message = aborted
    ? 'aborted'
    : error instanceof Error
      ? error.message
      : 'stream failed';
  set((state) => {
    const messages = state.messages.map((m) =>
      m.id === messageId ? {...m, streaming: false, error: aborted ? undefined : message} : m
    );
    const cache = Object.fromEntries(
      Object.entries(state.cache).map(([sid, list]) => {
        if (!list.some((m) => m.id === messageId)) return [sid, list];
        return [
          sid,
          list.map((m) =>
            m.id === messageId
              ? {...m, streaming: false, error: aborted ? undefined : message}
              : m
          )
        ];
      })
    );
    return {
      messages,
      cache,
      streaming: false,
      abortController: null,
      error: aborted ? state.error : message
    };
  });
  // Keep the function async-call-friendly by referencing get() to avoid a
  // dead-store warning on the unused getter.
  void get;
}
