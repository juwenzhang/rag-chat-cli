"use client";

import { usePathname, useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useFilteredSessions } from "@/features/chat/hooks/use-filtered-sessions";
import { activeSessionId } from "@/features/chat/utils/active-session-id";
import { api } from "@/lib/api/browser";
import type { SessionMeta, UserOut } from "@/lib/api/shared/types";

import { CollapsedSessionSidebar } from "./collapsed-session-sidebar";
import { SessionList } from "./session-list";
import { SessionSidebarHeader } from "./session-sidebar-header";

interface Props {
  user: UserOut;
  sessions: SessionMeta[];
}

/** Chat module sidebar — conversation list with create / rename / pin / delete. */
export function SessionSidebar({ sessions }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const currentId = activeSessionId(pathname);
  const [creating, startCreating] = useTransition();
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<SessionMeta | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);

  const filtered = useFilteredSessions(sessions, query);
  const pinnedCount = useMemo(
    () => filtered.filter((session) => session.pinned).length,
    [filtered]
  );

  const createNew = () =>
    startCreating(async () => {
      try {
        const meta = await api.chat.createSession();
        router.push(`/chat/${meta.id}`);
        router.refresh();
      } catch {
        toast.error("Failed to create conversation");
      }
    });

  const commitRename = async (session: SessionMeta, nextRaw: string) => {
    const next = nextRaw.trim();
    setRenamingId(null);
    if (!next || next === (session.title ?? "")) return;
    try {
      await api.chat.updateSession(session.id, { title: next });
      toast.success("Renamed");
      router.refresh();
    } catch {
      toast.error("Failed to rename");
    }
  };

  const togglePin = async (session: SessionMeta) => {
    const next = !session.pinned;
    try {
      await api.chat.updateSession(session.id, { pinned: next });
      toast.success(next ? "Pinned to top" : "Unpinned");
      router.refresh();
    } catch {
      toast.error(next ? "Failed to pin" : "Failed to unpin");
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const id = pendingDelete.id;
    try {
      await api.chat.deleteSession(id);
    } catch {
      toast.error("Failed to delete conversation");
      throw new Error("delete failed");
    }
    toast.success("Conversation deleted");
    if (currentId === id) router.push("/chat");
    router.refresh();
  };

  if (collapsed) {
    return (
      <CollapsedSessionSidebar
        creating={creating}
        onCreate={createNew}
        onExpand={() => setCollapsed(false)}
      />
    );
  }

  return (
    <aside className="hidden h-full w-72 shrink-0 flex-col border-r border-border bg-card/40 md:flex">
      <SessionSidebarHeader
        creating={creating}
        query={query}
        onCollapse={() => setCollapsed(true)}
        onCreate={createNew}
        onQueryChange={setQuery}
      />
      <SessionList
        sessions={filtered}
        query={query}
        pinnedCount={pinnedCount}
        currentId={currentId}
        renamingId={renamingId}
        onOpen={(session) => router.push(`/chat/${session.id}`)}
        onTogglePin={(session) => void togglePin(session)}
        onRequestRename={(session) => setRenamingId(session.id)}
        onCommitRename={(session, next) => void commitRename(session, next)}
        onCancelRename={() => setRenamingId(null)}
        onRequestDelete={setPendingDelete}
      />
      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Delete this conversation?"
        description={
          <>
            <span className="font-medium text-foreground">
              {pendingDelete?.title || "Untitled"}
            </span>{" "}
            and all of its messages will be permanently removed. This can&apos;t be
            undone.
          </>
        }
        confirmLabel="Delete"
        destructive
        onConfirm={confirmDelete}
      />
    </aside>
  );
}
