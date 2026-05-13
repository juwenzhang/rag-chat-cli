"use client";

import { ArrowLeft, Trash2, UserMinus, UserPlus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  WikiMemberOut,
  WikiOut,
  WikiRole,
  WikiVisibility,
} from "@/lib/api/types";
import { cn } from "@/lib/utils";

const WIKI_ROLES: WikiRole[] = ["editor", "viewer"];

interface Props {
  currentUserId: string;
  wiki: WikiOut;
  members: WikiMemberOut[];
}

export function WikiSettingsClient({ currentUserId, wiki, members: initialMembers }: Props) {
  const router = useRouter();
  const isOrgOwner = wiki.role === "owner";
  // Editor+ can rename; only org owner can change visibility / delete.
  const canEdit = wiki.role !== "viewer";
  const [members, setMembers] = useState(initialMembers);

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-16 pt-6 sm:px-8 sm:pt-10">
      <Button asChild variant="ghost" size="sm" className="mb-4 -ml-2">
        <Link href={`/wiki/${wiki.id}`}>
          <ArrowLeft />
          Back to {wiki.name}
        </Link>
      </Button>

      <h1 className="mb-1 text-2xl font-semibold tracking-tight">
        Wiki settings
      </h1>
      <p className="mb-6 text-sm text-muted-foreground">
        Manage <span className="font-medium">{wiki.name}</span> — rename it,
        change who can see it, or delete it.
      </p>

      <DetailsSection
        wiki={wiki}
        canEdit={canEdit}
        canChangeVisibility={isOrgOwner}
        onSaved={() => router.refresh()}
      />

      {wiki.visibility === "private" && (
        <MembersSection
          wikiId={wiki.id}
          currentUserId={currentUserId}
          isOrgOwner={isOrgOwner}
          members={members}
          onMembersChanged={setMembers}
        />
      )}

      {isOrgOwner && !wiki.is_default && (
        <DangerZone
          wikiName={wiki.name}
          onDeleted={() => {
            router.push("/wiki");
            router.refresh();
          }}
          wikiId={wiki.id}
        />
      )}
    </div>
  );
}

function DetailsSection({
  wiki,
  canEdit,
  canChangeVisibility,
  onSaved,
}: {
  wiki: WikiOut;
  canEdit: boolean;
  canChangeVisibility: boolean;
  onSaved: () => void;
}) {
  const [name, setName] = useState(wiki.name);
  const [description, setDescription] = useState(wiki.description ?? "");
  const [visibility, setVisibility] = useState<WikiVisibility>(wiki.visibility);
  const [busy, setBusy] = useState(false);

  const dirty =
    name.trim() !== wiki.name ||
    (description.trim() || null) !== (wiki.description || null) ||
    visibility !== wiki.visibility;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!dirty || busy) return;
    setBusy(true);
    try {
      const res = await fetch(`/api/wikis/${wiki.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim() !== wiki.name ? name.trim() : undefined,
          description:
            (description.trim() || null) !== (wiki.description || null)
              ? description.trim() || null
              : undefined,
          visibility:
            visibility !== wiki.visibility ? visibility : undefined,
        }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as {
          message?: string;
        };
        toast.error(body.message || "Failed to save");
        return;
      }
      toast.success("Saved");
      onSaved();
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={onSubmit}
      className={cn(
        "mb-8 space-y-4 rounded-xl border border-border bg-card p-5",
        !canEdit && "opacity-80"
      )}
    >
      <h2 className="text-base font-semibold">Details</h2>
      <div className="space-y-1.5">
        <Label htmlFor="wiki-name">Name</Label>
        <Input
          id="wiki-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          readOnly={!canEdit}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="wiki-desc">Description</Label>
        <Textarea
          id="wiki-desc"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          readOnly={!canEdit}
          rows={2}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="wiki-vis">Visibility</Label>
        <select
          id="wiki-vis"
          value={visibility}
          onChange={(e) => setVisibility(e.target.value as WikiVisibility)}
          disabled={!canChangeVisibility}
          className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm disabled:opacity-60"
        >
          <option value="org_wide">
            Workspace-wide — any workspace member can read
          </option>
          <option value="private">
            Private — only invited members
          </option>
        </select>
        {!canChangeVisibility && (
          <p className="text-[11px] text-muted-foreground">
            Only the workspace owner can change visibility.
          </p>
        )}
      </div>
      <div className="flex justify-end">
        <Button type="submit" disabled={!dirty || busy || !canEdit}>
          {busy ? "Saving…" : "Save changes"}
        </Button>
      </div>
    </form>
  );
}

function MembersSection({
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
    const res = await fetch(`/api/wikis/${wikiId}/members`);
    if (res.ok) {
      onMembersChanged((await res.json()) as WikiMemberOut[]);
    }
  };

  const onInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteEmail.trim() || inviting) return;
    setInviting(true);
    try {
      const res = await fetch(`/api/wikis/${wikiId}/members`, {
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
      await refresh();
    } finally {
      setInviting(false);
    }
  };

  const changeRole = async (userId: string, role: WikiRole) => {
    const res = await fetch(`/api/wikis/${wikiId}/members/${userId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    });
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { message?: string };
      toast.error(body.message || "Failed to update");
      return;
    }
    await refresh();
  };

  const remove = async (userId: string) => {
    const res = await fetch(`/api/wikis/${wikiId}/members/${userId}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { message?: string };
      toast.error(body.message || "Failed to remove");
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

function DangerZone({
  wikiId,
  wikiName,
  onDeleted,
}: {
  wikiId: string;
  wikiName: string;
  onDeleted: () => void;
}) {
  const [pending, setPending] = useState(false);

  const onConfirm = async () => {
    const res = await fetch(`/api/wikis/${wikiId}`, { method: "DELETE" });
    if (!res.ok) {
      const body = (await res.json().catch(() => ({}))) as { message?: string };
      toast.error(body.message || "Failed to delete");
      throw new Error("delete failed");
    }
    toast.success("Wiki deleted");
    onDeleted();
  };

  return (
    <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-5">
      <h2 className="text-base font-semibold text-destructive">Danger zone</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Deleting this wiki also deletes all of its pages. This can't be
        undone.
      </p>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setPending(true)}
        className="mt-3 border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
      >
        <Trash2 />
        Delete this wiki
      </Button>
      <ConfirmDialog
        open={pending}
        onOpenChange={setPending}
        title={`Delete ${wikiName}?`}
        description="All pages in this wiki will be removed permanently."
        confirmLabel="Delete"
        destructive
        onConfirm={onConfirm}
      />
    </div>
  );
}
