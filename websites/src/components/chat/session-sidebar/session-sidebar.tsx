"use client";

import {
  ChevronsLeft,
  ChevronsRight,
  MessageSquarePlus,
  Search,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { api } from "@/lib/api/browser";
import type { SessionMeta, UserOut } from "@/lib/api/types";

import { SessionRow } from "./session-row";

interface Props {
  user: UserOut;
  sessions: SessionMeta[];
}

function activeSessionId(pathname: string): string | null {
  const m = pathname.match(/^\/chat\/([^/]+)/);
  return m ? m[1] : null;
}

/** Chat module sidebar — conversation list with create / rename / pin / delete. */
export function SessionSidebar({ user: _user, sessions }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const currentId = activeSessionId(pathname);
  const [creating, startCreating] = useTransition();
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<SessionMeta | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);

  // Server already orders pinned-first, but we re-sort after filtering so
  // local query results keep the same grouping.
  const filtered = useMemo(() => {
    const base = query.trim()
      ? sessions.filter((s) =>
          (s.title ?? "Untitled").toLowerCase().includes(query.toLowerCase())
        )
      : sessions;
    return [...base].sort((a, b) => {
      const pa = a.pinned ? 1 : 0;
      const pb = b.pinned ? 1 : 0;
      if (pa !== pb) return pb - pa;
      return b.updated_at.localeCompare(a.updated_at);
    });
  }, [sessions, query]);

  const pinnedCount = useMemo(
    () => filtered.filter((s) => s.pinned).length,
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

  const commitRename = async (s: SessionMeta, nextRaw: string) => {
    const next = nextRaw.trim();
    setRenamingId(null);
    // No-op if unchanged or empty (empty title falls back to the message preview,
    // which is rarely what the user means by an explicit rename).
    if (!next || next === (s.title ?? "")) return;
    try {
      await api.chat.updateSession(s.id, { title: next });
      toast.success("Renamed");
      router.refresh();
    } catch {
      toast.error("Failed to rename");
    }
  };

  const togglePin = async (s: SessionMeta) => {
    const next = !s.pinned;
    try {
      await api.chat.updateSession(s.id, { pinned: next });
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
    if (currentId === id) {
      router.push("/chat");
    }
    router.refresh();
  };

  if (collapsed) {
    return (
      <aside className="flex h-full w-14 shrink-0 flex-col border-r border-border bg-card/50">
        <div className="flex flex-col items-center gap-1 p-2">
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setCollapsed(false)}
                  aria-label="Expand sidebar"
                >
                  <ChevronsRight />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">Expand</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={createNew}
                  disabled={creating}
                  aria-label="New conversation"
                >
                  <MessageSquarePlus />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">New conversation</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <div className="flex-1" />
      </aside>
    );
  }

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-border bg-card/40">
      {/* Brand */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <Link href="/chat" className="flex items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-md bg-brand-gradient text-white shadow shadow-primary/20">
            <span className="text-xs font-bold">R</span>
          </div>
          <span className="font-semibold tracking-tight">lhx-rag</span>
        </Link>
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setCollapsed(true)}
                aria-label="Collapse sidebar"
              >
                <ChevronsLeft />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">Collapse</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      {/* New conversation — module-scoped action, stays here since
          this sidebar is chat-specific. */}
      <div className="p-3">
        <Button onClick={createNew} disabled={creating} className="w-full">
          <MessageSquarePlus />
          {creating ? "Creating…" : "New conversation"}
        </Button>
      </div>

      {/* Search */}
      <div className="relative px-3 pb-3">
        <Search className="absolute left-6 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search conversations…"
          className="pl-9"
        />
      </div>

      {/* Sessions */}
      <ScrollArea className="flex-1 px-2 pb-2">
        {filtered.length === 0 ? (
          <p className="px-3 py-8 text-center text-xs text-muted-foreground">
            {query ? "No matches" : "No conversations yet"}
          </p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {filtered.map((s, i) => {
              const isFirstUnpinned =
                pinnedCount > 0 && !s.pinned && i === pinnedCount;
              return (
                <li key={s.id}>
                  {isFirstUnpinned && (
                    <div
                      className="mx-2 my-1 h-px bg-border/60"
                      aria-hidden
                    />
                  )}
                  <SessionRow
                    session={s}
                    active={s.id === currentId}
                    renaming={renamingId === s.id}
                    onOpen={() => router.push(`/chat/${s.id}`)}
                    onTogglePin={() => togglePin(s)}
                    onRequestRename={() => setRenamingId(s.id)}
                    onCommitRename={(next) => commitRename(s, next)}
                    onCancelRename={() => setRenamingId(null)}
                    onRequestDelete={() => setPendingDelete(s)}
                  />
                </li>
              );
            })}
          </ul>
        )}
      </ScrollArea>

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
            and all of its messages will be permanently removed. This can&apos;t
            be undone.
          </>
        }
        confirmLabel="Delete"
        destructive
        onConfirm={confirmDelete}
      />
    </aside>
  );
}
