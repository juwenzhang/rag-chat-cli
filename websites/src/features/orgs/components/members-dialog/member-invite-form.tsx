"use client";

import { UserPlus } from "lucide-react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Role } from "@/lib/api/shared/types";

export function MemberInviteForm({
  email,
  role,
  inviting,
  onEmailChange,
  onRoleChange,
  onSubmit,
}: {
  email: string;
  role: Role;
  inviting: boolean;
  onEmailChange: (next: string) => void;
  onRoleChange: (next: Role) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <form onSubmit={onSubmit} className="rounded-lg border border-border bg-muted/30 p-3">
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-[200px] flex-1 space-y-1.5">
          <Label htmlFor="invite-email" className="text-xs">
            Invite by email
          </Label>
          <Input
            id="invite-email"
            type="email"
            value={email}
            onChange={(event) => onEmailChange(event.target.value)}
            placeholder="user@example.com"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Role</Label>
          <select
            value={role}
            onChange={(event) => onRoleChange(event.target.value as Role)}
            className="h-9 rounded-md border border-border bg-background px-2 text-sm"
          >
            <option value="editor">Editor</option>
            <option value="viewer">Viewer</option>
          </select>
        </div>
        <Button type="submit" disabled={!email.trim() || inviting}>
          <UserPlus />
          {inviting ? "Inviting…" : "Invite"}
        </Button>
      </div>
    </form>
  );
}
