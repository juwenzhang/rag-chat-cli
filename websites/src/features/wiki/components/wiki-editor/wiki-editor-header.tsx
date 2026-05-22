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

export interface WikiEditorHeaderCopy {
  askAI: string;
  share: string;
  pageActions: string;
  duplicate: string;
  move: string;
  delete: string;
}

export function WikiEditorHeader({
  wiki,
  readOnly,
  status,
  lastSavedAt,
  copy,
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
  copy: WikiEditorHeaderCopy;
  onAskAI: () => void;
  onShare: () => void;
  onDuplicate: () => void;
  onMove: () => void;
  onDelete: () => void;
}) {
  return (
    <header className="flex h-12 shrink-0 items-center gap-1 border-b border-border bg-background/80 px-2 pl-14 backdrop-blur sm:gap-2 sm:px-3 md:pl-3">
      <Button asChild variant="ghost" size="sm" className="h-8 min-w-0 gap-1.5 px-2 sm:px-3">
        <Link href={`/wiki/${wiki.id}`}>
          <ArrowLeft className="size-3.5 shrink-0" />
          <span className="max-w-27.5 truncate sm:max-w-50">{wiki.name}</span>
        </Link>
      </Button>
      <div className="ml-auto flex shrink-0 items-center gap-1 text-xs text-muted-foreground sm:gap-2">
        <div className="hidden sm:block">
          <SaveIndicator status={status} lastSavedAt={lastSavedAt} />
        </div>
        <Button variant="outline" size="sm" onClick={onAskAI} className="h-8 px-2 sm:px-3">
          <MessageSquare className="size-3.5" />
          <span className="hidden sm:inline">{copy.askAI}</span>
        </Button>
        {readOnly ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 gap-1.5 px-2 sm:px-3"
            onClick={onShare}
          >
            <Share2 className="size-3.5" />
            <span className="hidden sm:inline">{copy.share}</span>
          </Button>
        ) : (
          <WikiPageActions
            copy={copy}
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
  copy,
  onShare,
  onDuplicate,
  onMove,
  onDelete,
}: {
  copy: WikiEditorHeaderCopy;
  onShare: () => void;
  onDuplicate: () => void;
  onMove: () => void;
  onDelete: () => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={copy.pageActions}>
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
          {copy.share}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onDuplicate}>
          <Copy />
          {copy.duplicate}
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault();
            onMove();
          }}
        >
          <Move />
          {copy.move}
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
          {copy.delete}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
