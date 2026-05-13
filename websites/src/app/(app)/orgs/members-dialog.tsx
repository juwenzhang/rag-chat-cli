"use client";

import { Crown, Loader2, UserMinus, UserPlus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { MemberOut, OrgOut, Role } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const ROLES: Role[] = ["owner", "editor", "viewer"];

export function MembersDialog({
  org,
  currentUserId,
  onClose,
}: {
  org: OrgOut | null;
  currentUserId: string;
  onClose: () => void;
}) {
  const open = org !== null;
  const [members, setMembers] = useState<MemberOut[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<Role>("editor");
  const [inviting, setInviting] = useState(false);

  const refresh = useCallback(async (orgId: string) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/orgs/${orgId}/members`);
      if (!res.ok) {
        toast.error("Failed to load members");
        return;
      }
      setMembers((await res.json()) as MemberOut[]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (org) {
      setMembers(null);
      void refresh(org.id);
    }
  }, [org, refresh]);

  const canManage = org?.role === "owner";

  const onInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!org || !inviteEmail.trim() || inviting) return;
    setInviting(true);
    try {
      const res = await fetch(`/api/orgs/${org.id}/members`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: inviteEmail.trim(),
          role: inviteRole,
        }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as {
          message?: string;
        };
        toast.error(body.message || "Failed to invite");
        return;
      }
      toast.success("Member added");
      setInviteEmail("");
      await refresh(org.id);
    } finally {
      setInviting(false);
    }
  };

  const changeRole = async (userId: string, role: Role) => {
    if (!org) return;
    const res = await fetch(`/api/orgs/${org.id}/members/${userId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { message?: string };
      toast.error(body.message || "Failed to update role");
      return;
    }
    await refresh(org.id);
  };

  const remove = async (userId: string) => {
    if (!org) return;
    const res = await fetch(`/api/orgs/${org.id}/members/${userId}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { message?: string };
      toast.error(body.message || "Failed to remove");
      return;
    }
    toast.success("Member removed");
    await refresh(org.id);
  };

  return (
    <Dialog open={open} onOpenChange={(n) => !n && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{org?.name ?? ""} · members</DialogTitle>
          <DialogDescription>
            Owners can invite people by email (they must already have an
            account) and change roles.
          </DialogDescription>
        </DialogHeader>

        {canManage && (
          <form
            onSubmit={onInvite}
            className="rounded-lg border border-border bg-muted/30 p-3"
          >
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-[200px] flex-1 space-y-1.5">
                <Label htmlFor="invite-email" className="text-xs">
                  Invite by email
                </Label>
                <Input
                  id="invite-email"
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="user@example.com"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Role</Label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as Role)}
                  className="h-9 rounded-md border border-border bg-background px-2 text-sm"
                >
                  <option value="editor">Editor</option>
                  <option value="viewer">Viewer</option>
                </select>
              </div>
              <Button
                type="submit"
                disabled={!inviteEmail.trim() || inviting}
              >
                <UserPlus />
                {inviting ? "Inviting…" : "Invite"}
              </Button>
            </div>
          </form>
        )}

        <div className="max-h-[40vh] space-y-1 overflow-y-auto">
          {loading && members === null ? (
            <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
            </div>
          ) : members && members.length > 0 ? (
            members.map((m) => {
              const isOwnerRow = m.role === "owner";
              const isSelf = m.user_id === currentUserId;
              return (
                <div
                  key={m.user_id}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-2 py-2",
                    "hover:bg-accent/50"
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate text-sm font-medium">
                        {m.display_name || m.email.split("@")[0]}
                      </span>
                      {isOwnerRow && (
                        <Crown className="size-3 shrink-0 text-primary" />
                      )}
                      {isSelf && (
                        <span className="rounded-full bg-muted px-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                          You
                        </span>
                      )}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {m.email}
                    </div>
                  </div>
                  {canManage && !isOwnerRow ? (
                    <>
                      <select
                        value={m.role}
                        onChange={(e) =>
                          void changeRole(m.user_id, e.target.value as Role)
                        }
                        className="h-8 rounded-md border border-border bg-background px-2 text-xs"
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {r}
                          </option>
                        ))}
                      </select>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => void remove(m.user_id)}
                        aria-label="Remove member"
                        className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                      >
                        <UserMinus />
                      </Button>
                    </>
                  ) : (
                    <span className="text-xs capitalize text-muted-foreground">
                      {m.role}
                    </span>
                  )}
                </div>
              );
            })
          ) : (
            <p className="py-4 text-center text-sm text-muted-foreground">
              No members yet.
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
