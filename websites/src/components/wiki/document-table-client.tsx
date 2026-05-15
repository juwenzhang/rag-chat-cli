"use client";

import { FileText, MoreHorizontal, Plus, Share2, Trash2 } from "lucide-react";
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
import { api } from "@/lib/api/browser";
import type { DocumentOut } from "@/lib/api/types";
import { cn, formatRelative } from "@/lib/utils";
import { PagePreviewHover } from "@/components/wiki/page-preview-hover";

interface Props {
  documents: DocumentOut[];
}

export function DocumentTableClient({ documents: initial }: Props) {
  const router = useRouter();
  const [docs, setDocs] = useState(initial);
  const [pendingDelete, setPendingDelete] = useState<DocumentOut | null>(null);
  const [creating, setCreating] = useState(false);

  const onCreateDocument = async () => {
    if (creating) return;
    setCreating(true);
    try {
      const doc = await api.documents.create({});
      router.push(`/wiki/documents/${doc.id}`);
      router.refresh();
    } catch {
      toast.error("Failed to create document");
    } finally {
      setCreating(false);
    }
  };

  const onDelete = async () => {
    if (!pendingDelete) return;
    try {
      await api.documents.remove(pendingDelete.id);
      setDocs((prev) => prev.filter((d) => d.id !== pendingDelete.id));
      toast.success("Document deleted");
    } catch {
      toast.error("Failed to delete");
    }
  };

  const onShare = async (doc: DocumentOut) => {
    const url = `${window.location.origin}/wiki/documents/${doc.id}`;
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Link copied");
    } catch {
      toast.error("Failed to copy link");
    }
  };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">
            Document Library
          </h2>
          <p className="text-xs text-muted-foreground">
            {docs.length} document{docs.length === 1 ? "" : "s"} — personal
            notes not linked to any wiki
          </p>
        </div>
        <Button size="sm" onClick={onCreateDocument} disabled={creating}>
          <Plus className="size-3.5" />
          {creating ? "Creating…" : "New document"}
        </Button>
      </div>

      {docs.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-card/40 p-10 text-center">
          <FileText className="mx-auto size-8 text-muted-foreground/50" />
          <p className="mt-3 text-sm font-medium">No documents yet</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Click &ldquo;New document&rdquo; to start writing.
          </p>
        </div>
      ) : (
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
              {docs.map((doc, i) => (
                <tr
                  key={doc.id}
                  className={cn(
                    "transition-colors hover:bg-accent/50",
                    i !== docs.length - 1 && "border-b border-border/60"
                  )}
                >
                  <td className="px-4 py-0">
                    <PagePreviewHover
                      type="document"
                      id={doc.id}
                      title={doc.title || "Untitled"}
                    >
                      <Link
                        href={`/wiki/documents/${doc.id}`}
                        className="flex items-center gap-2 py-3 text-foreground"
                      >
                        <FileText className="size-3.5 shrink-0 text-muted-foreground" />
                        <span className="truncate font-medium">
                          {doc.title || "Untitled"}
                        </span>
                      </Link>
                    </PagePreviewHover>
                  </td>
                  <td className="hidden px-4 py-3 text-xs text-muted-foreground sm:table-cell">
                    {formatRelative(doc.updated_at)}
                  </td>
                  <td className="hidden px-4 py-3 text-xs text-muted-foreground md:table-cell">
                    {formatRelative(doc.created_at)}
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
                        <DropdownMenuItem onSelect={() => onShare(doc)}>
                          <Share2 />
                          Copy link
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onSelect={(e) => {
                            e.preventDefault();
                            setPendingDelete(doc);
                          }}
                          className="text-destructive focus:bg-destructive/10 focus:text-destructive"
                        >
                          <Trash2 />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Delete this document?"
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
    </div>
  );
}
