"use client";

import { useMemo } from "react";

import type { SessionMeta } from "@/lib/api/shared/types";

/**
 * Memoized search + sort over the session list.
 *
 * Matching is case-insensitive against ``title`` (with the
 * ``"Untitled"`` fallback) so users can find draft conversations
 * the auto-titler hasn't yet renamed. Sort order: pinned first,
 * then newest ``updated_at``.
 */
export function useFilteredSessions(
  sessions: SessionMeta[],
  query: string
): SessionMeta[] {
  return useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const base = normalized
      ? sessions.filter((session) =>
          (session.title ?? "Untitled").toLowerCase().includes(normalized)
        )
      : sessions;
    return [...base].sort((a, b) => {
      const pinnedA = a.pinned ? 1 : 0;
      const pinnedB = b.pinned ? 1 : 0;
      if (pinnedA !== pinnedB) return pinnedB - pinnedA;
      return b.updated_at.localeCompare(a.updated_at);
    });
  }, [sessions, query]);
}
