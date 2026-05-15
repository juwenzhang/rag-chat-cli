"use client";

import { ArrowLeft, Book } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/browser";
import type { WikiVisibility } from "@/lib/api/types";

export function NewWikiClient({
  orgId,
  orgName,
}: {
  orgId: string;
  orgName: string;
}) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<WikiVisibility>("org_wide");
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      const wiki = await api.orgs.createWiki(orgId, {
        name: name.trim(),
        description: description.trim() || undefined,
        visibility,
      });
      toast.success("Wiki created");
      router.push(`/wiki/${wiki.id}`);
      router.refresh();
    } catch (err) {
      toast.error((err as Error).message || "Failed to create wiki");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-2xl px-4 pb-16 pt-6 sm:px-8 sm:pt-10">
      <Button asChild variant="ghost" size="sm" className="mb-4 -ml-2">
        <Link href="/wiki">
          <ArrowLeft />
          Back to wikis
        </Link>
      </Button>

      <header className="mb-6 flex items-start gap-3">
        <div className="flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Book className="size-5" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            New wiki in {orgName}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Group related pages into a named knowledge base. RAG will scope
            retrieval per-wiki, so this is also how you decide what the AI
            can see.
          </p>
        </div>
      </header>

      <form onSubmit={onSubmit} className="space-y-5">
        <div className="space-y-1.5">
          <Label htmlFor="name">Name</Label>
          <Input
            id="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Engineering notes"
            autoFocus
            required
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="description">
            Description{" "}
            <span className="text-xs text-muted-foreground">(optional)</span>
          </Label>
          <Textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="One-line summary of what lives here"
            rows={2}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="visibility">Visibility</Label>
          <select
            id="visibility"
            value={visibility}
            onChange={(e) => setVisibility(e.target.value as WikiVisibility)}
            className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
          >
            <option value="org_wide">
              Workspace-wide — any workspace member can read
            </option>
            <option value="private">
              Private — only the people you invite can read
            </option>
          </select>
          <p className="text-[11px] text-muted-foreground">
            You can change this later. Private wikis show their own member
            list in settings.
          </p>
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <Button asChild type="button" variant="ghost">
            <Link href="/wiki">Cancel</Link>
          </Button>
          <Button type="submit" disabled={!name.trim() || busy}>
            {busy ? "Creating…" : "Create wiki"}
          </Button>
        </div>
      </form>
    </div>
  );
}
