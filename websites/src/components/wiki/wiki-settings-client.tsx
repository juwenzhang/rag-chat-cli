"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { WikiMemberOut, WikiOut } from "@/lib/api/types";

import { WikiDangerZone } from "./wiki-danger-zone";
import { WikiDetailsSection } from "./wiki-details-section";
import { WikiMembersSection } from "./wiki-members-section";

interface Props {
  currentUserId: string;
  wiki: WikiOut;
  members: WikiMemberOut[];
}

/** Wiki settings page — details, membership (private wikis), danger zone. */
export function WikiSettingsClient({
  currentUserId,
  wiki,
  members: initialMembers,
}: Props) {
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

      <WikiDetailsSection
        wiki={wiki}
        canEdit={canEdit}
        canChangeVisibility={isOrgOwner}
        onSaved={() => router.refresh()}
      />

      {wiki.visibility === "private" && (
        <WikiMembersSection
          wikiId={wiki.id}
          currentUserId={currentUserId}
          isOrgOwner={isOrgOwner}
          members={members}
          onMembersChanged={setMembers}
        />
      )}

      {isOrgOwner && !wiki.is_default && (
        <WikiDangerZone
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
