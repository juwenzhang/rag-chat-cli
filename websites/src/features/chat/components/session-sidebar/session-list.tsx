"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import type { SessionMeta } from "@/lib/api/shared/types";

import { SessionRow } from "./session-row";

export function SessionList({
  sessions,
  query,
  pinnedCount,
  currentId,
  renamingId,
  onOpen,
  onTogglePin,
  onRequestRename,
  onCommitRename,
  onCancelRename,
  onRequestDelete,
}: {
  sessions: SessionMeta[];
  query: string;
  pinnedCount: number;
  currentId: string | null;
  renamingId: string | null;
  onOpen: (session: SessionMeta) => void;
  onTogglePin: (session: SessionMeta) => void;
  onRequestRename: (session: SessionMeta) => void;
  onCommitRename: (session: SessionMeta, next: string) => void;
  onCancelRename: () => void;
  onRequestDelete: (session: SessionMeta) => void;
}) {
  return (
    <ScrollArea className="flex-1 px-2 pb-2">
      {sessions.length === 0 ? (
        <p className="px-3 py-8 text-center text-xs text-muted-foreground">
          {query ? "No matches" : "No conversations yet"}
        </p>
      ) : (
        <ul className="flex flex-col gap-0.5">
          {sessions.map((session, index) => {
            const isFirstUnpinned =
              pinnedCount > 0 && !session.pinned && index === pinnedCount;
            return (
              <li key={session.id}>
                {isFirstUnpinned && (
                  <div className="mx-2 my-1 h-px bg-border/60" aria-hidden />
                )}
                <SessionRow
                  session={session}
                  active={session.id === currentId}
                  renaming={renamingId === session.id}
                  onOpen={() => onOpen(session)}
                  onTogglePin={() => onTogglePin(session)}
                  onRequestRename={() => onRequestRename(session)}
                  onCommitRename={(next) => onCommitRename(session, next)}
                  onCancelRename={onCancelRename}
                  onRequestDelete={() => onRequestDelete(session)}
                />
              </li>
            );
          })}
        </ul>
      )}
    </ScrollArea>
  );
}
