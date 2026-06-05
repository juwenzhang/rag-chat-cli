/**
 * Shared enums mirroring the backend wire protocol.
 *
 * Single source of truth for the TUI client. Backend counterparts:
 *   - service/streaming/error_codes.py (EventType / FlowErrorCode / TransportErrorCode)
 *   - service/llm/client.py (LLMError subclass `code` ClassVars)
 *   - docs/backend/STREAM_PROTOCOL.md and docs/backend/ERROR_CODES.md
 *
 * NEVER write the underlying string literals (``'token'``,
 * ``'llm_rate_limited'``, …) directly in consumers — import from here.
 */

export const StreamEventType = {
  Retrieval: 'retrieval',
  Token: 'token',
  Thought: 'thought',
  ToolCall: 'tool_call',
  ToolResult: 'tool_result',
  Done: 'done',
  Error: 'error',
  UserMessage: 'user_message'
} as const;
export type StreamEventType = (typeof StreamEventType)[keyof typeof StreamEventType];

export const ErrorCode = {
  // LLM upstream — owned by service.llm.client.LLMError subclasses.
  LlmRateLimited: 'llm_rate_limited',
  LlmSubscriptionRequired: 'llm_subscription_required',
  LlmUnauthorized: 'llm_unauthorized',
  LlmModelNotFound: 'llm_model_not_found',
  LlmUpstreamUnavailable: 'llm_upstream_unavailable',
  LlmError: 'llm_error',
  // ChatService flow.
  Aborted: 'ABORTED',
  RetrievalFailed: 'retrieval_failed',
  MemoryReadFailed: 'memory_read_failed',
  MemoryWriteFailed: 'memory_write_failed',
  MaxStepsReached: 'max_steps_reached',
  Unexpected: 'unexpected',
  // Transport.
  Protocol: 'PROTOCOL',
  Internal: 'INTERNAL',
  // Client-only.
  Parse: 'PARSE',
  TransportError: 'transport_error'
} as const;
export type ErrorCode = (typeof ErrorCode)[keyof typeof ErrorCode];

export const MessageRole = {
  User: 'user',
  Assistant: 'assistant',
  System: 'system',
  Tool: 'tool'
} as const;
export type MessageRole = (typeof MessageRole)[keyof typeof MessageRole];
