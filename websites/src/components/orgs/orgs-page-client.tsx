"use client";

import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { api } from "@/lib/api/browser";
import type { OrgOut } from "@/lib/api/types";

import { CreateOrgDialog } from "./create-org-dialog";
import { MembersDialog } from "./members-dialog";
import { OrgCard } from "./org-card";
import { RenameOrgDialog } from "./rename-org-dialog";

interface Props {
  currentUserId: string;
  orgs: OrgOut[];
}

/** Workspaces page — grid of org cards plus create/rename/members/delete. */
export function OrgsPageClient({ currentUserId, orgs }: Props) {
  const router = useRouter();
  const [createOpen, setCreateOpen] = useState(false);
  const [membersOf, setMembersOf] = useState<OrgOut | null>(null);
  const [pendingDelete, setPendingDelete] = useState<OrgOut | null>(null);
  const [renaming, setRenaming] = useState<OrgOut | null>(null);
  const [pendingLeave, setPendingLeave] = useState<OrgOut | null>(null);

  const onLeave = async () => {
    if (!pendingLeave) return;
    try {
      await api.orgs.removeMember(pendingLeave.id, currentUserId);
    } catch (err) {
      toast.error((err as Error).message || "Failed to leave");
      throw err;
    }
    toast.success("Left workspace");
    router.refresh();
  };

  const onDelete = async () => {
    if (!pendingDelete) return;
    try {
      await api.orgs.remove(pendingDelete.id);
    } catch (err) {
      toast.error((err as Error).message || "Failed to delete workspace");
      throw err;
    }
    toast.success("Workspace deleted");
    router.refresh();
  };

  return (
    <div className="mx-auto w-full max-w-5xl px-4 pb-16 pt-6 sm:px-6 sm:pt-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1.5">
          <p className="text-[11px] font-medium uppercase tracking-wider text-primary">
            Workspaces
          </p>
          <h1 className="text-2xl font-semibold leading-tight tracking-tight sm:text-3xl">
            工作空间
          </h1>
          <p className="text-sm text-muted-foreground">
            Each workspace has its own wiki and members. Your personal workspace
            is auto-created and can&apos;t be deleted.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus />
          New workspace
        </Button>
      </header>

      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {orgs.map((o) => (
          <li key={o.id}>
            <OrgCard
              org={o}
              isOwner={o.role === "owner"}
              onRename={() => setRenaming(o)}
              onManageMembers={() => setMembersOf(o)}
              onDelete={() => setPendingDelete(o)}
              onLeave={() => setPendingLeave(o)}
            />
          </li>
        ))}
      </ul>

      <CreateOrgDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => router.refresh()}
      />

      <RenameOrgDialog
        org={renaming}
        onClose={() => setRenaming(null)}
        onRenamed={() => {
          router.refresh();
        }}
      />

      <MembersDialog
        org={membersOf}
        currentUserId={currentUserId}
        onClose={() => setMembersOf(null)}
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title={`Delete ${pendingDelete?.name ?? "this workspace"}?`}
        description="All wiki pages and members in this workspace will be removed. This cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={onDelete}
      />

      <ConfirmDialog
        open={pendingLeave !== null}
        onOpenChange={(open) => {
          if (!open) setPendingLeave(null);
        }}
        title={`Leave ${pendingLeave?.name ?? "this workspace"}?`}
        description="You'll lose access to its wiki and members. An owner will have to re-invite you to come back."
        confirmLabel="Leave"
        destructive
        onConfirm={onLeave}
      />
    </div>
  );
}
