import { ErrorCode } from "@/lib/api/shared/enums";
import type { ErrorPayload } from "@/lib/api/shared/types";

export type ErrorVariant =
  | { kind: "subscription"; href: string }
  | { kind: "rateLimited" }
  | { kind: "unauthorized" }
  | { kind: "modelNotFound" }
  | { kind: "generic" };

/**
 * Map a backend ``error`` payload to a UI display variant. Keeps the
 * switch statement (and the ``ErrorCode`` exhaustiveness) out of the
 * presentational component.
 */
export function pickErrorVariant(error: ErrorPayload): ErrorVariant {
  switch (error.code) {
    case ErrorCode.LlmSubscriptionRequired:
      return {
        kind: "subscription",
        href: error.upstream_url ?? "https://ollama.com/upgrade",
      };
    case ErrorCode.LlmRateLimited:
      return { kind: "rateLimited" };
    case ErrorCode.LlmUnauthorized:
      return { kind: "unauthorized" };
    case ErrorCode.LlmModelNotFound:
      return { kind: "modelNotFound" };
    default:
      return { kind: "generic" };
  }
}
