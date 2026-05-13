"use client";

import {
  Building2,
  Crown,
  LogOut,
  Pencil,
  Plus,
  Trash2,
  Users,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { OrgOut } from "@/lib/api/types";
import { cn, formatRelative } from "@/lib/utils";

import { MembersDialog } from "./members-dialog";

interface Props {
  currentUserId: string;
  orgs: OrgOut[];
}

export function OrgsPageClient({ currentUserId, orgs }: Props) {
  const router = useRouter();
  const [createOpen, setCreateOpen] = useState(false);
  const [membersOf, setMembersOf] = useState<OrgOut | null>(null);
  const [pendingDelete, setPendingDelete] = useState<OrgOut | null>(null);
  const [renaming, setRenaming] = useState<OrgOut | null>(null);
  const [pendingLeave, setPendingLeave] = useState<OrgOut | null>(null);

  const onLeave = async () => {
    if (!pendingLeave) return;
    const res = await fetch(
      `/api/orgs/${pendingLeave.id}/members/${currentUserId}`,
      { method: "DELETE" }
    );
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { message?: string };
      toast.error(body.message || "Failed to leave");
      throw new Error("leave failed");
    }
    toast.success("Left workspace");
    router.refresh();
  };

  const onDelete = async () => {
    if (!pendingDelete) return;
    const res = await fetch(`/api/orgs/${pendingDelete.id}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { message?: string };
      toast.error(body.message || "Failed to delete workspace");
      throw new Error("delete failed");
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
            is auto-created and can't be deleted.
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

function OrgCard({
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

function RenameOrgDialog({
  org,
  onClose,
  onRenamed,
}: {
  org: OrgOut | null;
  onClose: () => void;
  onRenamed: () => void;
}) {
  const [name, setName] = useState(org?.name ?? "");
  const [busy, setBusy] = useState(false);

  // Re-seed the input when a different org opens the dialog.
  useEffect(() => {
    setName(org?.name ?? "");
  }, [org]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!org || !name.trim() || busy || name.trim() === org.name) {
      onClose();
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(`/api/orgs/${org.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as {
          message?: string;
        };
        toast.error(body.message || "Failed to rename");
        return;
      }
      toast.success("Workspace renamed");
      onRenamed();
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={org !== null} onOpenChange={(n) => !n && onClose()}>
      <DialogContent className="max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Rename workspace</DialogTitle>
            <DialogDescription>
              Workspace slug stays the same so existing URLs keep working.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label htmlFor="rename-name" className="sr-only">
              Name
            </Label>
            <Input
              id="rename-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || busy}>
              {busy ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function CreateOrgDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      const res = await fetch("/api/orgs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          slug: slug.trim() || undefined,
        }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as {
          message?: string;
        };
        toast.error(body.message || "Failed to create");
        return;
      }
      toast.success("Workspace created");
      setName("");
      setSlug("");
      onOpenChange(false);
      onCreated();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Create workspace</DialogTitle>
            <DialogDescription>
              A workspace owns its own wiki pages and member list. You become
              the owner.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-4">
            <div className="space-y-1.5">
              <Label htmlFor="org-name">Name</Label>
              <Input
                id="org-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My team's workspace"
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="org-slug">Slug (optional)</Label>
              <Input
                id="org-slug"
                value={slug}
                onChange={(e) => setSlug(e.target.value.toLowerCase())}
                placeholder="auto-derived from name"
              />
              <p className="text-[11px] text-muted-foreground">
                Lowercase letters, digits, hyphens. Used in URLs.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || busy}>
              {busy ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
