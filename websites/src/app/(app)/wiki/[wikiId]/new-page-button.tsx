"use client";

import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { WikiPageDetailOut } from "@/lib/api/types";

export function NewPageButton({ wikiId }: { wikiId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  const onClick = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await fetch(`/api/wikis/${wikiId}/pages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (!res.ok) {
        toast.error("Failed to create page");
        return;
      }
      const page = (await res.json()) as WikiPageDetailOut;
      router.push(`/wiki/${wikiId}/p/${page.id}`);
      router.refresh();
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
