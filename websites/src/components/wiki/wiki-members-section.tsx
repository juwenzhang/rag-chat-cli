"use client";

import { UserMinus, UserPlus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/browser";
import type { WikiMemberOut, WikiRole } from "@/lib/api/types";

const WIKI_ROLES: WikiRole[] = ["editor", "viewer"];

/** Private-wiki membership management — invite, change role, remove. */
export function WikiMembersSection({
  wikiId,
  currentUserId,
  isOrgOwner,
  members,
  onMembersChanged,
}: {
  wikiId: string;
  currentUserId: string;
  isOrgOwner: boolean;
  members: WikiMemberOut[];
  onMembersChanged: (next: WikiMemberOut[]) => void;
}) {
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<WikiRole>("editor");
  const [inviting, setInviting] = useState(false);

  const refresh = async () => {
    try {
      onMembersChanged(await api.wikis.listMembers(wikiId));
    } catch {
      // Non-fatal — the list just stays as-is until the next change.
    }
  };

  const onInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim() || inviting) return;
    setInviting(true);
    try {
      await api.wikis.addMember(wikiId, {
        email: inviteEmail.trim(),
        role: inviteRole,
      });
      toast.success("Member added");
      setInviteEmail("");
      await refresh();
    } catch (err) {
      toast.error((err as Error).message || "Failed to invite");
    } finally {
      setInviting(false);
    }
  };

  const changeRole = async (userId: string, role: WikiRole) => {
    try {
      await api.wikis.updateMemberRole(wikiId, userId, { role });
      await refresh();
    } catch (err) {
      toast.error((err as Error).message || "Failed to update");
    }
  };

  const remove = async (userId: string) => {
    try {
      await api.wikis.removeMember(wikiId, userId);
    } catch (err) {
      toast.error((err as Error).message || "Failed to remove");
      return;
    }
    toast.success("Removed");
    await refresh();
  };

  return (
    <div className="mb-8 space-y-4 rounded-xl border border-border bg-card p-5">
      <div>
        <h2 className="text-base font-semibold">Members</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Private wiki — only people listed below can read or edit.
        </p>
      </div>

      {isOrgOwner && (
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
                onChange={(e) => setInviteRole(e.target.value as WikiRole)}
                className="h-9 rounded-md border border-border bg-background px-2 text-sm"
              >
                <option value="editor">Editor</option>
                <option value="viewer">Viewer</option>
              </select>
            </div>
            <Button type="submit" disabled={!inviteEmail.trim() || inviting}>
              <UserPlus />
              {inviting ? "Inviting…" : "Invite"}
            </Button>
          </div>
        </form>
      )}

      <div className="space-y-1">
        {members.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            No explicit members yet. The workspace owner sees this wiki
            regardless.
          </p>
        ) : (
          members.map((m) => {
            const isSelf = m.user_id === currentUserId;
            return (
              <div
                key={m.user_id}
                className="flex items-center gap-3 rounded-md px-2 py-2 hover:bg-accent/50"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-sm font-medium">
                      {m.display_name || m.email.split("@")[0]}
                    </span>
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
                {isOrgOwner ? (
                  <>
                    <select
                      value={m.role}
                      onChange={(e) =>
                        void changeRole(m.user_id, e.target.value as WikiRole)
                      }
                      className="h-8 rounded-md border border-border bg-background px-2 text-xs"
                    >
                      {WIKI_ROLES.map((r) => (
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
        )}
      </div>
    </div>
  );
}
