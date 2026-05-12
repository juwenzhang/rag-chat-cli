import "server-only";

import { apiFetch, apiStream } from "@/lib/api/client";
import type { MessageOut, SessionMeta, StreamEvent } from "@/lib/api/types";

export interface ListSessionsResult {
  items: SessionMeta[];
}

export async function listSessions(token: string): Promise<SessionMeta[]> {
  const data = await apiFetch<ListSessionsResult | SessionMeta[]>(
    "/chat/sessions",
    { token }
  );
  return Array.isArray(data) ? data : data.items;
}

export interface CreateSessionBody {
  title?: string | null;
  provider_id?: string | null;
  model?: string | null;
}

export async function createSession(
  token: string,
  bodyOrTitle?: CreateSessionBody | string
): Promise<SessionMeta> {
  const body: CreateSessionBody =
    typeof bodyOrTitle === "string" || bodyOrTitle === undefined
      ? { title: bodyOrTitle ?? null }
      : bodyOrTitle;
  return apiFetch<SessionMeta>("/chat/sessions", {
    method: "POST",
    token,
    body,
  });
}

export interface UpdateSessionBody {
  title?: string;
  provider_id?: string;
  model?: string;
  clear_provider_id?: boolean;
  clear_model?: boolean;
}

export async function updateSession(
  token: string,
  sessionId: string,
  body: UpdateSessionBody
): Promise<SessionMeta> {
  return apiFetch<SessionMeta>(`/chat/sessions/${sessionId}`, {
    method: "PATCH",
    token,
    body,
  });
}

export async function getMessages(
  token: string,
  sessionId: string
): Promise<MessageOut[]> {
  const data = await apiFetch<{ items: MessageOut[] } | MessageOut[]>(
    `/chat/sessions/${sessionId}/messages`,
    { token }
  );
  return Array.isArray(data) ? data : data.items;
}

export interface ChatStreamParams {
  session_id: string;
  content: string;
  use_rag?: boolean;
}

/**
 * Open the SSE stream from FastAPI. Returns the raw Response so the route
 * handler can pipe its body straight to the browser unchanged.
 */
export async function openChatStream(
  token: string,
  body: ChatStreamParams
): Promise<Response> {
  return apiStream("/chat/stream", {
    method: "POST",
    token,
    body,
  });
}

/**
 * Parse an SSE byte stream into typed StreamEvent objects.
 *
 * The FastAPI side emits frames shaped:
 *   event: token
 *   data: {"delta":"hello"}
 *
 * We accumulate by lines, split on blank-line boundaries, and yield one
 * parsed event per frame. Unknown event types fall through as `error`.
 */
export async function* parseSseStream(
  stream: ReadableStream<Uint8Array>
): AsyncGenerator<StreamEvent, void, unknown> {
  const reader = stream.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const parsed = parseFrame(frame);
        if (parsed) yield parsed;
      }
    }
    // Trailing frame if no closing blank line
    if (buffer.trim()) {
      const parsed = parseFrame(buffer);
      if (parsed) yield parsed;
    }
  } finally {
    reader.releaseLock();
  }
}

function parseFrame(frame: string): StreamEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith(":")) continue; // SSE comment / keepalive
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  const raw = dataLines.join("\n");
  try {
    const data = JSON.parse(raw);
    return { type: event, data } as StreamEvent;
  } catch {
    return { type: "error", data: { code: "PARSE", message: raw } };
  }
}
