import type { KnowledgeHit, ToolCallOut } from "@/lib/api/types";

export interface UIMessage {
  /** Local id (uuid-ish) — distinct from backend id during streaming. */
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Tool invocations the assistant requested during this turn. */
  toolCalls?: ToolCallOut[];
  /** Tool results spliced back into this turn. */
  toolResults?: Array<{ id: string; name: string; output: string; error?: string }>;
  /** RAG hits surfaced before generation. */
  retrieval?: KnowledgeHit[];
  /** True while the SSE stream is still appending. */
  streaming?: boolean;
  /** Failure message if the stream errored out. */
  error?: string;
}
