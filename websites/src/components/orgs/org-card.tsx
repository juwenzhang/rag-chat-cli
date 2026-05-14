"use client";

import { Building2, Crown, LogOut, Pencil, Trash2, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { OrgOut } from "@/lib/api/types";
import { cn, formatRelative } from "@/lib/utils";

/** Workspace card on the orgs grid — role badge + member/rename/delete actions. */
export function OrgCard({
  org,
  isOwner,
  onRename,
  onManageMembers,
  onDelete,
  onLeave,
}: {
  org: OrgOut;
  isOwner: boolean;
  onRename: () => void;
  onManageMembers: () => void;
  onDelete: () => void;
  onLeave: () => void;
}) {
  return (
    <div
      className={cn(
        "flex h-full flex-col rounded-xl border border-border bg-card p-4",
        "transition-all hover:border-primary/40 hover:shadow-md"
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand-gradient text-white">
          <Building2 className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <h3 className="truncate text-base font-semibold">{org.name}</h3>
            {org.is_personal && (
              <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                Personal
              </span>
            )}
          </div>
          <p className="truncate text-xs text-muted-foreground">{org.slug}</p>
        </div>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        {isOwner ? (
          <span className="inline-flex items-center gap-1 text-primary">
            <Crown className="size-3" />
            owner
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 capitalize">
            {org.role}
          </span>
        )}
        <span className="mx-2 text-border">·</span>
        created {formatRelative(org.created_at)}
      </p>
      <div className="mt-auto flex items-center gap-2 pt-4">
        <Button
          variant="outline"
          size="sm"
          onClick={onManageMembers}
          className="flex-1"
        >
          <Users />
          Members
        </Button>
        {isOwner && (
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onRename}
            aria-label="Rename workspace"
            className="text-muted-foreground hover:text-foreground"
          >
            <Pencil />
          </Button>
        )}
        {isOwner && !org.is_personal && (
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onDelete}
            aria-label="Delete workspace"
            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 />
          </Button>
        )}
        {!isOwner && !org.is_personal && (
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onLeave}
            aria-label="Leave workspace"
            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          >
            <LogOut />
          </Button>
        )}
      </div>
    </div>
  );
}
