"use client";

import { Crown, Loader2, UserMinus } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { MemberOut, Role } from "@/lib/api/shared/types";
import { cn } from "@/lib/utils";

const ROLES: Role[] = ["owner", "editor", "viewer"];

export function MembersList({
  members,
  loading,
  canManage,
  currentUserId,
  onChangeRole,
  onRemove,
}: {
  members: MemberOut[] | null;
  loading: boolean;
  canManage: boolean;
  currentUserId: string;
  onChangeRole: (userId: string, role: Role) => void;
  onRemove: (userId: string) => void;
}) {
  return (
    <div className="max-h-[40vh] space-y-1 overflow-y-auto">
      {loading && members === null ? (
        <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
        </div>
      ) : members && members.length > 0 ? (
        members.map((member) => (
          <MemberRow
            key={member.user_id}
            member={member}
            canManage={canManage}
            isSelf={member.user_id === currentUserId}
            onChangeRole={onChangeRole}
            onRemove={onRemove}
          />
        ))
      ) : (
        <p className="py-4 text-center text-sm text-muted-foreground">
          No members yet.
        </p>
      )}
    </div>
  );
}

function MemberRow({
  member,
  canManage,
  isSelf,
  onChangeRole,
  onRemove,
}: {
  member: MemberOut;
  canManage: boolean;
  isSelf: boolean;
  onChangeRole: (userId: string, role: Role) => void;
  onRemove: (userId: string) => void;
}) {
  const isOwnerRow = member.role === "owner";

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-md px-2 py-2",
        "hover:bg-accent/50"
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-sm font-medium">
            {member.display_name || member.email.split("@")[0]}
          </span>
          {isOwnerRow && <Crown className="size-3 shrink-0 text-primary" />}
          {isSelf && (
            <span className="rounded-full bg-muted px-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
              You
            </span>
          )}
        </div>
        <div className="truncate text-xs text-muted-foreground">
          {member.email}
        </div>
      </div>
      {canManage && !isOwnerRow ? (
        <>
          <select
            value={member.role}
            onChange={(event) =>
              onChangeRole(member.user_id, event.target.value as Role)
            }
            className="h-8 rounded-md border border-border bg-background px-2 text-xs"
          >
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => onRemove(member.user_id)}
            aria-label="Remove member"
            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          >
            <UserMinus />
          </Button>
        </>
      ) : (
        <span className="text-xs capitalize text-muted-foreground">
          {member.role}
        </span>
      )}
    </div>
  );
}
