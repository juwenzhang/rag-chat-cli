"use client";

import {
  ChevronsLeft,
  ChevronsRight,
  MessageSquarePlus,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Search,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { SessionMeta, UserOut } from "@/lib/api/types";
import { cn, formatRelative } from "@/lib/utils";

interface Props {
  user: UserOut;
  sessions: SessionMeta[];
}

function activeSessionId(pathname: string): string | null {
  const m = pathname.match(/^\/chat\/([^/]+)/);
  return m ? m[1] : null;
}

export function SessionSidebar({ user, sessions }: Props) {
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
      const res = await fetch("/api/chat/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        toast.error("Failed to create conversation");
        return;
      }
      const meta = (await res.json()) as SessionMeta;
      router.push(`/chat/${meta.id}`);
      router.refresh();
    });

  const commitRename = async (s: SessionMeta, nextRaw: string) => {
    const next = nextRaw.trim();
    setRenamingId(null);
    // No-op if unchanged or empty (empty title falls back to the message preview,
    // which is rarely what the user means by an explicit rename).
    if (!next || next === (s.title ?? "")) return;
    const res = await fetch(`/api/chat/sessions/${s.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: next }),
    });
    if (!res.ok) {
      toast.error("Failed to rename");
      return;
    }
    toast.success("Renamed");
    router.refresh();
  };

  const togglePin = async (s: SessionMeta) => {
    const next = !s.pinned;
    const res = await fetch(`/api/chat/sessions/${s.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pinned: next }),
    });
    if (!res.ok) {
      toast.error(next ? "Failed to pin" : "Failed to unpin");
      return;
    }
    toast.success(next ? "Pinned to top" : "Unpinned");
    router.refresh();
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const id = pendingDelete.id;
    const res = await fetch(`/api/chat/sessions/${id}`, { method: "DELETE" });
    if (!res.ok) {
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
        <Button
          onClick={createNew}
          disabled={creating}
          className="w-full"
        >
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

function SessionRow({
  session,
  active,
  renaming,
  onOpen,
  onTogglePin,
  onRequestRename,
  onCommitRename,
  onCancelRename,
  onRequestDelete,
}: {
  session: SessionMeta;
  active: boolean;
  renaming: boolean;
  onOpen: () => void;
  onTogglePin: () => void;
  onRequestRename: () => void;
  onCommitRename: (next: string) => void;
  onCancelRename: () => void;
  onRequestDelete: () => void;
}) {
  return (
    <div
      className={cn(
        "group relative flex items-center rounded-md transition-all",
        !renaming && "hover:bg-accent/60",
        active && !renaming && "bg-accent text-accent-foreground shadow-sm",
        renaming && "bg-primary/10 ring-1 ring-primary/30"
      )}
    >
      {renaming ? (
        <RenameInput
          initial={session.title ?? ""}
          onCommit={onCommitRename}
          onCancel={onCancelRename}
        />
      ) : (
        <button
          type="button"
          onClick={onOpen}
          onDoubleClick={(e) => {
            e.preventDefault();
            onRequestRename();
          }}
          className="min-w-0 flex-1 px-3 py-2 text-left"
        >
          <div className="flex items-center gap-1.5">
            {session.pinned && (
              <Pin
                aria-hidden
                className="size-3 shrink-0 text-primary"
                strokeWidth={2.5}
              />
            )}
            <span
              className={cn(
                "truncate text-sm font-medium",
                active ? "text-foreground" : "text-foreground/85"
              )}
            >
              {session.title || "Untitled"}
            </span>
          </div>
          <div className="mt-0.5 text-xs text-muted-foreground">
            {formatRelative(session.updated_at)}
          </div>
        </button>
      )}
      {!renaming && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Conversation actions"
              onClick={(e) => e.stopPropagation()}
              className={cn(
                "mr-1 size-7 shrink-0 text-muted-foreground opacity-0 transition-opacity",
                "group-hover:opacity-100 focus-visible:opacity-100",
                "data-[state=open]:opacity-100",
                (active || session.pinned) && "opacity-70"
              )}
            >
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuItem
              onSelect={(e) => {
                e.preventDefault();
                onRequestRename();
              }}
            >
              <Pencil />
              Rename
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={(e) => {
                e.preventDefault();
                onTogglePin();
              }}
            >
              {session.pinned ? (
                <>
                  <PinOff />
                  Unpin
                </>
              ) : (
                <>
                  <Pin />
                  Pin to top
                </>
              )}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={(e) => {
                e.preventDefault();
                onRequestDelete();
              }}
              className="text-destructive focus:bg-destructive/10 focus:text-destructive"
            >
              <Trash2 />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}

function RenameInput({
  initial,
  onCommit,
  onCancel,
}: {
  initial: string;
  onCommit: (next: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initial);
  const inputRef = useRef<HTMLInputElement>(null);
  // Guard against double-fire (Enter then blur).
  const committed = useRef(false);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const commit = () => {
    if (committed.current) return;
    committed.current = true;
    onCommit(value);
  };

  return (
    <div className="min-w-0 flex-1 px-2 py-1.5">
      <Input
        ref={inputRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          } else if (e.key === "Escape") {
            e.preventDefault();
            committed.current = true;
            onCancel();
          }
        }}
        onBlur={commit}
        maxLength={256}
        aria-label="Rename conversation"
        className="h-8 text-sm"
      />
    </div>
  );
}

