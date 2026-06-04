/**
 * DTOs that mirror the FastAPI schemas in api/schemas/.
 *
 * Keep these in sync with websites/src/lib/api/shared/types.ts. The TUI only
 * consumes a narrow slice of the full surface — auth, sessions, messages and
 * streaming are enough for Phase 1.
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
  token_type: 'bearer';
  access_expires_at: string;
  refresh_expires_at: string;
}

export interface SessionMeta {
  id: string;
  title: string | null;
  provider_id?: string | null;
  model?: string | null;
  pinned?: boolean;
  created_at: string;
  updated_at: string;
  message_count?: number;
}

export interface ToolCallOut {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface AnswerSource {
  source_type: 'document' | 'web' | 'image' | 'tool';
  rank: number;
  title?: string | null;
  quote?: string | null;
  score?: number | null;
  source?: string | null;
  url?: string | null;
  document_id?: string | null;
  chunk_id?: string | null;
}

export interface KnowledgeHit {
  document_id: string;
  chunk_id: string;
  score: number;
  content: string;
  title?: string | null;
  source?: string | null;
}

export interface MessageOut {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  tool_call_id?: string | null;
  tool_calls?: ToolCallOut[] | null;
  sources?: AnswerSource[] | null;
  created_at: string;
}

export type ThinkMode = boolean | 'low' | 'medium' | 'high';

export type StreamEvent =
  | {type: 'retrieval'; data: {hits: KnowledgeHit[]}}
  | {type: 'token'; data: {delta: string}}
  | {type: 'thought'; data: {text: string}}
  | {
      type: 'tool_call';
      data: {
        tool_call_id: string;
        tool_name: string;
        arguments: Record<string, unknown>;
      };
    }
  | {
      type: 'tool_result';
      data: {
        tool_call_id: string;
        tool_name: string;
        content: string;
        is_error?: boolean;
      };
    }
  | {
      type: 'done';
      data: {
        message_id?: string;
        usage?: Record<string, number>;
        duration_ms?: number;
        sources?: AnswerSource[] | null;
        model?: string | null;
        provider_name?: string | null;
      };
    }
  | {type: 'error'; data: {code: string; message: string}};

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
