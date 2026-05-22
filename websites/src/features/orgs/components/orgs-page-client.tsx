"use client";

import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { orgService } from "@/features/orgs/services/org-service";
import type { OrgOut } from "@/lib/api/shared/types";
import { useI18n } from "@/lib/i18n/provider";

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
  const { t } = useI18n();
  const [createOpen, setCreateOpen] = useState(false);
  const [membersOf, setMembersOf] = useState<OrgOut | null>(null);
  const [pendingDelete, setPendingDelete] = useState<OrgOut | null>(null);
  const [renaming, setRenaming] = useState<OrgOut | null>(null);
  const [pendingLeave, setPendingLeave] = useState<OrgOut | null>(null);

  const onLeave = async () => {
    if (!pendingLeave) return;
    try {
      await orgService.leaveOrg(pendingLeave.id, currentUserId);
    } catch (err) {
      toast.error((err as Error).message || t("orgs.leaveFailed"));
      throw err;
    }
    toast.success(t("orgs.left"));
    router.refresh();
  };

  const onDelete = async () => {
    if (!pendingDelete) return;
    try {
      await orgService.deleteOrg(pendingDelete.id);
    } catch (err) {
      toast.error((err as Error).message || t("orgs.deleteFailed"));
      throw err;
    }
    toast.success(t("orgs.deleted"));
    router.refresh();
  };

  return (
    <div className="mx-auto w-full max-w-5xl px-4 pb-16 pt-6 sm:px-6 sm:pt-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1.5">
          <p className="text-[11px] font-medium uppercase tracking-wider text-primary">
            {t("orgs.title")}
          </p>
          <h1 className="text-2xl font-semibold leading-tight tracking-tight sm:text-3xl">
            {t("orgs.heading")}
          </h1>
          <p className="text-sm text-muted-foreground">{t("orgs.description")}</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus />
          {t("orgs.new")}
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
        title={t("orgs.deleteTitle", {
          name: pendingDelete?.name ?? t("orgs.deleteFallback"),
        })}
        description={t("orgs.deleteDescription")}
        confirmLabel={t("common.delete")}
        destructive
        onConfirm={onDelete}
      />

      <ConfirmDialog
        open={pendingLeave !== null}
        onOpenChange={(open) => {
          if (!open) setPendingLeave(null);
        }}
        title={t("orgs.leaveTitle", {
          name: pendingLeave?.name ?? t("orgs.deleteFallback"),
        })}
        description={t("orgs.leaveDescription")}
        confirmLabel={t("common.leave")}
        destructive
        onConfirm={onLeave}
      />
    </div>
  );
}
