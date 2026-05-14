"use client";

import {
  ChevronDown,
  ChevronRight,
  FileText,
  MoreHorizontal,
  Plus,
  Trash2,
} from "lucide-react";
import Link from "next/link";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { WikiPageListOut } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** A single page-tree row — expand toggle, title link, hover actions. */
export function PageRow({
  wikiId,
  page,
  depth,
  active,
  canEdit,
  expanded,
  onToggleExpand,
  onAddChild,
  onRequestDelete,
}: {
  wikiId: string;
  page: WikiPageListOut;
  depth: number;
  active: boolean;
  canEdit: boolean;
  expanded?: boolean;
  onToggleExpand?: () => void;
  onAddChild: () => void;
  onRequestDelete: () => void;
}) {
  return (
    <div
      className={cn(
        "group relative flex items-center rounded-md transition-colors",
        "hover:bg-accent/60",
        active && "bg-accent text-accent-foreground"
      )}
      style={{ paddingLeft: 8 + depth * 14 }}
    >
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onToggleExpand?.();
        }}
        disabled={onToggleExpand === undefined}
        className={cn(
          "flex size-4 items-center justify-center rounded text-muted-foreground transition-colors",
          onToggleExpand && "hover:bg-muted hover:text-foreground"
        )}
        aria-label={expanded ? "Collapse" : "Expand"}
      >
        {expanded === undefined ? null : expanded ? (
          <ChevronDown className="size-3" />
        ) : (
          <ChevronRight className="size-3" />
        )}
      </button>

      <Link
        href={`/wiki/${wikiId}/p/${page.id}`}
        className="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 pl-1 pr-1 text-sm"
      >
        <FileText className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="truncate">{page.title || "Untitled"}</span>
      </Link>

      {canEdit && (
        <div className="flex items-center pr-1 opacity-0 transition-opacity group-hover:opacity-100">
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onAddChild();
            }}
            aria-label="Add child page"
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Plus className="size-3" />
          </button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                }}
                aria-label="Page menu"
                className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <MoreHorizontal className="size-3" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuItem
                onSelect={() => onRequestDelete()}
                className="text-destructive focus:bg-destructive/10 focus:text-destructive"
              >
                <Trash2 />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}
    </div>
  );
}
