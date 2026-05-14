"use client";

import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/browser";

export function NewPageButton({ wikiId }: { wikiId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  const onClick = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const page = await api.wikis.createPage(wikiId, {});
      router.push(`/wiki/${wikiId}/p/${page.id}`);
      router.refresh();
    } catch {
      toast.error("Failed to create page");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button onClick={onClick} disabled={busy} size="sm">
      <Plus />
      {busy ? "Creating…" : "New page"}
    </Button>
  );
}
