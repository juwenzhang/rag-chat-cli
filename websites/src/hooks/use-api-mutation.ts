"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiError } from "@/lib/api/types";

interface UseApiMutationResult<TArgs extends unknown[], TResult> {
  /**
   * Run the mutation. Resolves with the result on success; **re-throws**
   * `ApiError` on failure so the caller can `try/catch` and decide how to
   * surface it (usually `toast.error(err.message)`).
   */
  mutate: (...args: TArgs) => Promise<TResult>;
  /** True while a `mutate` call is in flight. Drives button spinners / disabled state. */
  mutating: boolean;
  /** The last error thrown by `mutate`, or `null`. Cleared at the start of each call. */
  error: ApiError | Error | null;
}

/**
 * Write-side counterpart to `useApiQuery`. Wraps a browser API call so
 * components stop hand-rolling a `saving` flag around every POST/PATCH/
 * DELETE:
 *
 *   const { mutate: rename, mutating } = useApiMutation(
 *     (id: string, title: string) => api.chat.updateSession(id, { title })
 *   );
 *
 * `mutate` re-throws on failure (rather than swallowing) because call
 * sites differ on how to react — toast, inline error, optimistic
 * rollback — and that decision belongs to them, not here.
 */
export function useApiMutation<TArgs extends unknown[], TResult>(
  mutator: (...args: TArgs) => Promise<TResult>
): UseApiMutationResult<TArgs, TResult> {
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState<ApiError | Error | null>(null);

  // Keep a stable `mutate` even when `mutator` is an inline arrow (new
  // identity each render): the latest mutator is mirrored into a ref,
  // synced after commit so `mutate` always calls the current one.
  const mutatorRef = useRef(mutator);
  useEffect(() => {
    mutatorRef.current = mutator;
  });

  const mutate = useCallback(async (...args: TArgs): Promise<TResult> => {
    setMutating(true);
    setError(null);
    try {
      return await mutatorRef.current(...args);
    } catch (err) {
      setError(err as ApiError | Error);
      throw err;
    } finally {
      setMutating(false);
    }
  }, []);

  return { mutate, mutating, error };
}
