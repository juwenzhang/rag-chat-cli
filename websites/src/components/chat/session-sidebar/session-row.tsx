"use client";

import { MoreHorizontal, Pencil, Pin, PinOff, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { SessionMeta } from "@/lib/api/types";
import { cn, formatRelative } from "@/lib/utils";

import { RenameInput } from "./rename-input";

/** One conversation row — title + relative time, inline rename, action menu. */
export function SessionRow({
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
