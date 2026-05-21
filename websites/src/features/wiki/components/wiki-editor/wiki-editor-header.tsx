"use client";

import {
  ArrowLeft,
  Copy,
  MessageSquare,
  MoreHorizontal,
  Move,
  Share2,
  Trash2,
} from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { WikiOut } from "@/lib/api/shared/types";

import { SaveIndicator, type WikiSaveStatus } from "../save-indicator";

export function WikiEditorHeader({
  wiki,
  readOnly,
  status,
  lastSavedAt,
  onAskAI,
  onShare,
  onDuplicate,
  onMove,
  onDelete,
}: {
  wiki: WikiOut;
  readOnly: boolean;
  status: WikiSaveStatus;
  lastSavedAt: Date | null;
  onAskAI: () => void;
  onShare: () => void;
  onDuplicate: () => void;
  onMove: () => void;
  onDelete: () => void;
}) {
  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border bg-background/80 px-3 backdrop-blur">
      <Button asChild variant="ghost" size="sm" className="h-8 gap-1.5">
        <Link href={`/wiki/${wiki.id}`}>
          <ArrowLeft className="size-3.5" />
          <span className="max-w-[200px] truncate">{wiki.name}</span>
        </Link>
      </Button>
      <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
        <SaveIndicator status={status} lastSavedAt={lastSavedAt} />
        <Button variant="outline" size="sm" onClick={onAskAI} className="h-8">
          <MessageSquare className="size-3.5" />
          Ask AI
        </Button>
        {readOnly ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 gap-1.5"
            onClick={onShare}
          >
            <Share2 className="size-3.5" />
            Share
          </Button>
        ) : (
          <WikiPageActions
            onShare={onShare}
            onDuplicate={onDuplicate}
            onMove={onMove}
            onDelete={onDelete}
          />
        )}
      </div>
    </header>
  );
}

function WikiPageActions({
  onShare,
  onDuplicate,
  onMove,
  onDelete,
}: {
  onShare: () => void;
  onDuplicate: () => void;
  onMove: () => void;
  onDelete: () => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="Page actions">
          <MoreHorizontal />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault();
            onShare();
          }}
        >
          <Share2 />
          Share
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onDuplicate}>
          <Copy />
          Duplicate
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault();
            onMove();
          }}
        >
          <Move />
          Move to wiki…
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault();
            onDelete();
          }}
          className="text-destructive focus:bg-destructive/10 focus:text-destructive"
        >
          <Trash2 />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
