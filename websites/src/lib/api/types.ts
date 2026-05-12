/**
 * DTOs that mirror the FastAPI schemas in api/schemas/.
 *
 * Keep this in sync with docs/openapi.json. The shapes are intentionally
 * narrow — only the fields the web client actually reads.
 */

export interface UserOut {
  id: string;
  email: string;
  display_name: string | null;
  is_active: boolean;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  access_expires_at: string;
  refresh_expires_at: string;
}

export interface SessionMeta {
  id: string;
  title: string | null;
  /** Per-session provider pin (Sprint 2). `null` means "use user default". */
  provider_id?: string | null;
  /** Per-session model pin (Sprint 2). `null` means "use user default". */
  model?: string | null;
  created_at: string;
  updated_at: string;
  message_count?: number;
}

/** A configured LLM provider belonging to the current user. */
export interface ProviderOut {
  id: string;
  name: string;
  type: "ollama" | "openai";
  base_url: string;
  has_api_key: boolean;
  is_default: boolean;
  enabled: boolean;
}

export interface ModelListItem {
  id: string;
  size: number | null;
}

export interface UserPreferenceOut {
  default_provider_id: string | null;
  default_model: string | null;
  default_use_rag: boolean;
}

export interface ConnectivityTestOut {
  ok: boolean;
  detail: string;
}

export interface MessageOut {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  tool_call_id?: string | null;
  tool_calls?: ToolCallOut[] | null;
  created_at: string;
}

export interface ToolCallOut {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface DocumentOut {
  id: string;
  title: string;
  source?: string | null;
  chunk_count: number;
  created_at: string;
}

export interface KnowledgeHit {
  document_id: string;
  chunk_id: string;
  score: number;
  content: string;
  title?: string | null;
}

/** Streaming event vocabulary — mirrors core/streaming/events.py */
export type StreamEvent =
  | { type: "retrieval"; data: { hits: KnowledgeHit[] } }
  | { type: "token"; data: { delta: string } }
  | { type: "thought"; data: { content: string } }
  | { type: "tool_call"; data: { id: string; name: string; arguments: Record<string, unknown> } }
  | { type: "tool_result"; data: { id: string; name: string; output: string; error?: string } }
  | { type: "done"; data: { message_id?: string; usage?: Record<string, number> } }
  | { type: "error"; data: { code: string; message: string } };

/** A failed API response with a structured payload. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}
