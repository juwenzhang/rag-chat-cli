"use client";

import {
  FileText,
  MoreHorizontal,
  Share2,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { WikiPageShareDialog } from "@/components/wiki/wiki-page-share-dialog";
import { PagePreviewHover } from "@/components/wiki/page-preview-hover";
import { api } from "@/lib/api/browser";
import type { WikiPageListOut } from "@/lib/api/types";
import { cn, formatRelative } from "@/lib/utils";

interface Props {
  wikiId: string;
  pages: WikiPageListOut[];
  canEdit: boolean;
}

export function PageTableClient({ wikiId, pages: initial, canEdit }: Props) {
  const router = useRouter();
  const [pages, setPages] = useState(initial);
  const [pendingDelete, setPendingDelete] =
    useState<WikiPageListOut | null>(null);
  const [shareTarget, setShareTarget] =
    useState<WikiPageListOut | null>(null);

  const onDelete = async () => {
    if (!pendingDelete) return;
    try {
      await api.wikiPages.remove(pendingDelete.id);
      setPages((prev) => prev.filter((p) => p.id !== pendingDelete.id));
      toast.success("Page deleted");
      router.refresh();
    } catch {
      toast.error("Failed to delete");
    }
  };

  return (
    <>
      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/30">
            <tr className="text-left text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-2.5">Title</th>
              <th className="hidden px-4 py-2.5 sm:table-cell w-40">
                Last updated
              </th>
              <th className="hidden px-4 py-2.5 md:table-cell w-32">
                Created
              </th>
              <th className="px-4 py-2.5 w-16 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {pages.map((p, i) => (
              <tr
                key={p.id}
                className={cn(
                  "transition-colors hover:bg-accent/50",
                  i !== pages.length - 1 && "border-b border-border/60"
                )}
              >
                <td className="px-4 py-0">
                  <PagePreviewHover
                    type="wiki-page"
                    id={p.id}
                    title={p.title || "Untitled"}
                  >
                    <Link
                      href={`/wiki/${wikiId}/p/${p.id}`}
                      className="flex items-center gap-2 py-3 text-foreground"
                    >
                      <FileText className="size-3.5 shrink-0 text-muted-foreground" />
                      <span className="truncate font-medium">
                        {p.title || "Untitled"}
                      </span>
                    </Link>
                  </PagePreviewHover>
                </td>
                <td className="hidden px-4 py-3 text-xs text-muted-foreground sm:table-cell">
                  {formatRelative(p.updated_at)}
                </td>
                <td className="hidden px-4 py-3 text-xs text-muted-foreground md:table-cell">
                  {formatRelative(p.created_at)}
                </td>
                <td className="px-4 py-3 text-right">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label="Actions"
                      >
                        <MoreHorizontal className="size-3.5" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-36">
                      <DropdownMenuItem
                        onSelect={(e) => {
                          e.preventDefault();
                          setShareTarget(p);
                        }}
                      >
                        <Share2 />
                        Share
                      </DropdownMenuItem>
                      {canEdit && (
                        <DropdownMenuItem
                          onSelect={(e) => {
                            e.preventDefault();
                            setPendingDelete(p);
                          }}
                          className="text-destructive focus:bg-destructive/10 focus:text-destructive"
                        >
                          <Trash2 />
                          Delete
                        </DropdownMenuItem>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Delete this page?"
        description={
          <>
            &ldquo;
            <span className="font-medium text-foreground">
              {pendingDelete?.title || "Untitled"}
            </span>
            &rdquo; will be removed permanently.
          </>
        }
        confirmLabel="Delete"
        destructive
        onConfirm={onDelete}
      />

      {shareTarget && (
        <WikiPageShareDialog
          open={shareTarget !== null}
          onOpenChange={(open) => {
            if (!open) setShareTarget(null);
          }}
          pageId={shareTarget.id}
          pageTitle={shareTarget.title || "Untitled"}
        />
      )}
    </>
  );
}
