"use client";

import { CloudDownload, Pencil, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  VirtualTable,
  type VirtualTableColumn,
} from "@/components/ui/virtual-table";
import type { ModelListItem } from "@/lib/api/types";

/** Virtualised model list for one provider card — name, size, note, actions. */
export function ModelTable({
  models,
  providerType,
  onEdit,
  onDelete,
}: {
  models: ModelListItem[];
  providerType: string;
  onEdit: (model: ModelListItem) => void;
  onDelete: (modelId: string) => void;
}) {
  const isOllama = providerType === "ollama";

  const columns: VirtualTableColumn<ModelListItem>[] = [
    {
      key: "name",
      header: "Model",
      width: "minmax(220px, 2.5fr)",
      cell: (m) => (
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="truncate font-mono text-[13px] text-foreground">
            {m.id}
          </span>
          {m.kind === "embedding" && (
            <Badge
              variant="secondary"
              className="shrink-0 px-1 py-0 text-[9px] uppercase tracking-wide"
            >
              embed
            </Badge>
          )}
          {m.id.toLowerCase().endsWith("-cloud") && (
            <Badge
              variant="outline"
              className="shrink-0 gap-1 px-1 py-0 text-[9px] uppercase tracking-wide text-primary"
            >
              <CloudDownload className="size-2.5" />
              cloud
            </Badge>
          )}
        </div>
      ),
    },
    {
      key: "size",
      header: "Size",
      width: "84px",
      align: "right",
      cell: (m) =>
        m.size != null ? (
          <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
            {formatSize(m.size)}
          </span>
        ) : (
          <span className="text-[11px] text-muted-foreground/50">—</span>
        ),
    },
    {
      key: "desc",
      header: "Description",
      width: "minmax(0, 3fr)",
      cell: (m) =>
        m.description ? (
          <span
            className="line-clamp-2 text-[12px] leading-snug text-muted-foreground"
            title={m.description}
          >
            {m.description}
          </span>
        ) : (
          <button
            type="button"
            onClick={() => onEdit(m)}
            className="text-[11px] italic text-muted-foreground/60 underline-offset-2 hover:text-foreground hover:underline"
          >
            add a note…
          </button>
        ),
    },
    {
      key: "actions",
      header: "",
      width: isOllama ? "76px" : "44px",
      align: "right",
      cell: (m) => (
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onEdit(m);
            }}
            aria-label={`Edit description for ${m.id}`}
            className="rounded-md p-1.5 text-muted-foreground/70 transition-colors hover:bg-foreground/10 hover:text-foreground"
          >
            <Pencil className="size-3.5" />
          </button>
          {isOllama && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(m.id);
              }}
              aria-label={`Delete model ${m.id}`}
              className="rounded-md p-1.5 text-muted-foreground/70 transition-colors hover:bg-destructive/10 hover:text-destructive"
            >
              <Trash2 className="size-3.5" />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <VirtualTable
      rows={models}
      rowKey={(m) => m.id}
      columns={columns}
      estimatedRowHeight={48}
      maxHeight={420}
      density="comfortable"
    />
  );
}

function formatSize(bytes: number): string {
  if (bytes <= 0) return "";
  const units = ["B", "K", "M", "G", "T"];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(n < 10 ? 1 : 0)}${units[i]}`;
}
