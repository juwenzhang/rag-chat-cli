"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { orgService } from "@/features/orgs/services/org-service";
import type { MemberOut, OrgOut, Role } from "@/lib/api/shared/types";

import { MemberInviteForm } from "./member-invite-form";
import { MembersList } from "./members-list";

/** Org membership dialog — invite by email, change roles, remove members. */
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
    setMembers(null);
    setLoading(true);
    try {
      setMembers(await orgService.listMembers(orgId));
    } catch {
      toast.error("Failed to load members");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!org) return;
    const id = window.setTimeout(() => void refresh(org.id), 0);
    return () => window.clearTimeout(id);
  }, [org, refresh]);

  const canManage = org?.role === "owner";

  const onInvite = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!org || !inviteEmail.trim() || inviting) return;
    setInviting(true);
    try {
      await orgService.addMember(org.id, {
        email: inviteEmail.trim(),
        role: inviteRole,
      });
      toast.success("Member added");
      setInviteEmail("");
      await refresh(org.id);
    } catch (err) {
      toast.error((err as Error).message || "Failed to invite");
    } finally {
      setInviting(false);
    }
  };

  const changeRole = async (userId: string, role: Role) => {
    if (!org) return;
    try {
      await orgService.updateMemberRole(org.id, userId, { role });
      await refresh(org.id);
    } catch (err) {
      toast.error((err as Error).message || "Failed to update role");
    }
  };

  const remove = async (userId: string) => {
    if (!org) return;
    try {
      await orgService.removeMember(org.id, userId);
    } catch (err) {
      toast.error((err as Error).message || "Failed to remove");
      return;
    }
    toast.success("Member removed");
    await refresh(org.id);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{org?.name ?? ""} · members</DialogTitle>
          <DialogDescription>
            Owners can invite people by email (they must already have an account) and
            change roles.
          </DialogDescription>
        </DialogHeader>

        {canManage && (
          <MemberInviteForm
            email={inviteEmail}
            role={inviteRole}
            inviting={inviting}
            onEmailChange={setInviteEmail}
            onRoleChange={setInviteRole}
            onSubmit={onInvite}
          />
        )}

        <MembersList
          members={members}
          loading={loading}
          canManage={canManage}
          currentUserId={currentUserId}
          onChangeRole={(userId, role) => void changeRole(userId, role)}
          onRemove={(userId) => void remove(userId)}
        />
      </DialogContent>
    </Dialog>
  );
}
