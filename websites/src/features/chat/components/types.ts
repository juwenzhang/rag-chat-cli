import type {
  AnswerSource,
  ErrorPayload,
  KnowledgeHit,
  MessageEvaluationOut,
  ToolCallOut,
} from "@/lib/api/shared/types";

export interface UIMessage {
  /** Local id (uuid-ish) — distinct from backend id during streaming. */
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Product-level thinking / action trace surfaced by the backend. */
  thoughts?: string[];
  /** Tool invocations the assistant requested during this turn. */
  toolCalls?: ToolCallOut[];
  /** Tool results spliced back into this turn. */
  toolResults?: Array<{ id: string; name: string; output: string; error?: string }>;
  /** RAG hits surfaced before generation. */
  retrieval?: KnowledgeHit[];
  /** Normalized answer sources persisted by the backend. */
  sources?: AnswerSource[];
  /** Optional AI quality evaluation for this answer. */
  evaluation?: MessageEvaluationOut;
  /** True while the SSE stream is still appending. */
  streaming?: boolean;
  /** Structured failure payload if the stream errored out. */
  error?: ErrorPayload;
  /** Resolved model / provider the backend used to produce this turn. */
  model?: string | null;
  provider?: string | null;
  /** Token usage breakdown from the done event. */
  usage?: Record<string, number>;
  /** Wall-clock duration the backend reported for this turn. */
  durationMs?: number;
  /**
   * True if the row originated from the server's messages table (so ``id``
   * is the real UUID and per-message actions like Share / Bookmark can
   * reference it). Optimistic rows added during the live stream stay false
   * until the post-stream refetch swaps in real ids.
   */
  persisted?: boolean;
}
