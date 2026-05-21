"use client";

import {
  Book,
  ChevronsLeft,
  ChevronsUpDown,
  Lock,
  Plus,
  Trash2,
} from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { OrgOut, WikiOut } from "@/lib/api/shared/types";

export function WikiSwitcher({
  activeOrg,
  activeWiki,
  wikis,
  canCreateWiki,
  onCollapse,
  onCreateWiki,
  onRequestDeleteWiki,
}: {
  activeOrg: OrgOut;
  activeWiki: WikiOut | null;
  wikis: WikiOut[];
  canCreateWiki: boolean;
  onCollapse: () => void;
  onCreateWiki: () => void;
  onRequestDeleteWiki: (wiki: WikiOut) => void;
}) {
  return (
    <div className="border-b border-border px-3 py-3">
      <p className="truncate text-[10px] uppercase tracking-wider text-muted-foreground">
        {activeOrg.name}
      </p>
      <div className="mt-1 flex items-center gap-1">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex min-w-0 flex-1 items-center gap-1.5 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-accent"
            >
              <Book className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate text-sm font-semibold">
                {activeWiki ? activeWiki.name : "All wikis"}
              </span>
              {activeWiki?.visibility === "private" && (
                <Lock className="size-3 shrink-0 text-muted-foreground" />
              )}
              <ChevronsUpDown className="size-3 shrink-0 text-muted-foreground" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-60">
            <DropdownMenuLabel>Wikis in {activeOrg.name}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {wikis.length === 0 && (
              <p className="px-2 py-2 text-xs text-muted-foreground">
                No wikis yet.
              </p>
            )}
            {wikis.map((wiki) => (
              <DropdownMenuItem key={wiki.id} asChild>
                <Link
                  href={`/wiki/${wiki.id}`}
                  className="flex items-center gap-2"
                >
                  <Book className="size-3.5 text-muted-foreground" />
                  <span className="flex-1 truncate">{wiki.name}</span>
                  {wiki.visibility === "private" && (
                    <Lock className="size-3 text-muted-foreground" />
                  )}
                </Link>
              </DropdownMenuItem>
            ))}
            {canCreateWiki && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={(event) => {
                    event.preventDefault();
                    onCreateWiki();
                  }}
                >
                  <Plus />
                  New wiki…
                </DropdownMenuItem>
              </>
            )}
            {activeWiki && activeOrg.role === "owner" && (
              <DropdownMenuItem
                onSelect={(event) => {
                  event.preventDefault();
                  onRequestDeleteWiki(activeWiki);
                }}
                className="text-destructive focus:bg-destructive/10 focus:text-destructive"
              >
                <Trash2 />
                Delete this wiki
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onCollapse}
          aria-label="Collapse sidebar"
        >
          <ChevronsLeft />
        </Button>
      </div>
    </div>
  );
}
