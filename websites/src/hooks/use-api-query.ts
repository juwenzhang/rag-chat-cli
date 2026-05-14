"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiError } from "@/lib/api/types";

interface UseApiQueryOptions<T> {
  /**
   * Seed value — typically data the Server Component already fetched and
   * passed down as a prop. When provided, `loading` starts `false` and
   * the fetcher only runs on `refetch()` or when `deps` change.
   */
  initialData?: T;
  /** When `false`, the fetcher is not run (useful for lazy/conditional loads). */
  enabled?: boolean;
  /** Re-run the fetcher whenever any of these values change. */
  deps?: readonly unknown[];
}

interface UseApiQueryResult<T> {
  data: T | undefined;
  error: ApiError | Error | null;
  loading: boolean;
  /** Trigger a re-run of the fetcher (e.g. after a mutation). */
  refetch: () => void;
}

/**
 * Read-side data hook for the browser API client. Collapses the
 * fetch + `loading` + `error` + `refetch` boilerplate that every Client
 * Component was hand-rolling into one call:
 *
 *   const { data, loading, error, refetch } = useApiQuery(
 *     () => api.providers.list(),
 *     { initialData: initialProviders }
 *   );
 *
 * Deliberately minimal — no cache, no dedup, no revalidation. It owns
 * exactly one request's lifecycle and drops the result of a superseded
 * run (deps changed, unmounted) via a per-run `cancelled` flag; anything
 * fancier is a state-management concern, not this.
 */
export function useApiQuery<T>(
  fetcher: () => Promise<T>,
  options: UseApiQueryOptions<T> = {}
): UseApiQueryResult<T> {
  const { initialData, enabled = true, deps = [] } = options;

  const [data, setData] = useState<T | undefined>(initialData);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(enabled && initialData === undefined);
  // Bumped by `refetch()` to re-run the fetch effect on demand.
  const [reloadToken, setReloadToken] = useState(0);

  // The fetcher is almost always an inline arrow (new identity each
  // render), so re-runs are driven off `deps`/`enabled`/`reloadToken`,
  // not the fetcher. Its latest value is mirrored into a ref, synced
  // after commit.
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const refetch = useCallback(() => {
    setReloadToken((t) => t + 1);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    // Per-run flag — the cleanup flips it so a late resolution from a
    // superseded run (deps changed, or the component unmounted) can't
    // clobber fresher state.
    let cancelled = false;

    // A data-fetching effect legitimately marks `loading` before kicking
    // the request; the actual result lands via the promise callbacks
    // below, which is the sanctioned "external system" pattern.
    /* eslint-disable react-hooks/set-state-in-effect */
    setLoading(true);
    setError(null);
    /* eslint-enable react-hooks/set-state-in-effect */

    fetcherRef
      .current()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err as ApiError | Error);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, reloadToken, ...deps]);

  return { data, error, loading, refetch };
}
