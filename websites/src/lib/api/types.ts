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
  /** Pinned sessions float to the top of the sidebar. */
  pinned?: boolean;
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
  /** ``"embedding"`` means this model is meant for vectorisation, not chat. */
  kind?: "chat" | "embedding";
  /** User-authored free-text note shown as a hover tooltip in pickers. */
  description?: string | null;
}

export interface UserPreferenceOut {
  default_provider_id: string | null;
  default_model: string | null;
  default_embedding_model: string | null;
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
  source: string;
  created_at: string;
  updated_at: string;
}

/** Full document with body for editing. */
export interface DocumentDetailOut extends DocumentOut {
  /** Markdown body. */
  body: string;
}

export interface KnowledgeHit {
  document_id: string;
  chunk_id: string;
  score: number;
  content: string;
  title?: string | null;
}

/** A single message rendered inside a public share / bookmark payload. */
export interface SharedMessage {
  role: "user" | "assistant";
  content: string;
  tokens: number | null;
  model: string | null;
  provider_name: string | null;
  created_at: string;
}

/** ``GET /shares/{token}`` — public, no auth required. */
export interface SharePublicOut {
  token: string;
  created_at: string;
  session_id: string;
  /** Lets the page show "Continue here" (owner) vs "Fork" (everyone else). */
  session_owner_id: string;
  user_message: SharedMessage;
  assistant_message: SharedMessage;
}

/** Owner-facing share record returned by POST /shares and GET /shares. */
export interface ShareOut {
  id: string;
  token: string;
  session_id: string;
  user_message_id: string;
  assistant_message_id: string;
  created_at: string;
}

/** Lightweight bookmark row — refs only. */
export interface BookmarkOut {
  id: string;
  session_id: string;
  user_message_id: string;
  assistant_message_id: string;
  note: string | null;
  created_at: string;
}

/** Bookmark joined with its Q&A — what the bookmarks page renders. */
export interface BookmarkDetailOut {
  id: string;
  session_id: string;
  session_owner_id: string;
  /** Message refs so the page can trigger Share against the same Q&A. */
  user_message_id: string;
  assistant_message_id: string;
  note: string | null;
  created_at: string;
  user_message: SharedMessage;
  assistant_message: SharedMessage;
}

/** Streaming event vocabulary — mirrors core/streaming/events.py */
export type StreamEvent =
  | { type: "retrieval"; data: { hits: KnowledgeHit[] } }
  | { type: "token"; data: { delta: string } }
  | { type: "thought"; data: { text: string } }
  | {
      type: "tool_call";
      data: {
        tool_call_id: string;
        tool_name: string;
        arguments: Record<string, unknown>;
      };
    }
  | {
      type: "tool_result";
      data: {
        tool_call_id: string;
        tool_name: string;
        content: string;
        is_error?: boolean;
      };
    }
  | {
      type: "done";
      data: {
        message_id?: string;
        usage?: Record<string, number>;
        duration_ms?: number;
        /** The model the backend actually resolved for this answer. */
        model?: string | null;
        /** Friendly name of the provider that produced this answer. */
        provider_name?: string | null;
      };
    }
  | { type: "error"; data: { code: string; message: string } };

/* ─────────────────────────────────────────────────────────────────
   Orgs and Wiki — Notion/Lark-style workspaces + block-based pages
   ───────────────────────────────────────────────────────────────── */

export type Role = "owner" | "editor" | "viewer";

export interface OrgOut {
  id: string;
  slug: string;
  name: string;
  owner_id: string;
  is_personal: boolean;
  created_at: string;
  updated_at: string;
  /** The caller's role in this org. */
  role: Role;
}

export interface MemberOut {
  user_id: string;
  email: string;
  display_name: string | null;
  role: Role;
  created_at: string;
}

export type WikiVisibility = "org_wide" | "private";
export type WikiRole = "editor" | "viewer";

/** Owner reflects the org owner; everywhere else is editor/viewer. */
export type EffectiveWikiRole = "owner" | "editor" | "viewer";

export interface WikiOut {
  id: string;
  org_id: string;
  slug: string;
  name: string;
  description: string | null;
  created_by_user_id: string;
  is_default: boolean;
  visibility: WikiVisibility;
  created_at: string;
  updated_at: string;
  role: EffectiveWikiRole;
}

export interface WikiMemberOut {
  user_id: string;
  email: string;
  display_name: string | null;
  role: WikiRole;
  created_at: string;
}

export interface WikiPageListOut {
  id: string;
  wiki_id: string;
  parent_id: string | null;
  title: string;
  position: number;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface WikiPageDetailOut extends WikiPageListOut {
  /** Markdown source. */
  body: string;
  created_by_user_id: string;
}

// ── Wiki page shares ────────────────────────────────────────────────

/** Owner-facing wiki page share record. */
export interface WikiPageShareOut {
  id: string;
  token: string;
  page_id: string;
  created_at: string;
}

/** ``GET /wiki-page-shares/{token}`` — public, no auth required. */
export interface WikiPageSharePublicOut {
  token: string;
  created_at: string;
  page_id: string;
  page_title: string;
  page_body: string;
  wiki_name: string;
  shared_by_display_name: string | null;
}

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
