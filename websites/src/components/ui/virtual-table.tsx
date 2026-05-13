"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import {
  useEffect,
  useRef,
  type CSSProperties,
  type ReactNode,
} from "react";

import { cn } from "@/lib/utils";

export interface VirtualTableColumn<T> {
  /** Stable column identifier — used for React key + a11y. */
  key: string;
  header: ReactNode;
  /**
   * CSS Grid track value. ``"minmax(0, 1fr)"`` for flexible columns,
   * ``"auto"`` for content-sized, ``"80px"`` for fixed.
   */
  width: string;
  align?: "left" | "right" | "center";
  /** Extra class on both header and body cells (e.g. font-mono). */
  cellClassName?: string;
  /** Body cell renderer. */
  cell: (row: T) => ReactNode;
}

export interface VirtualTableProps<T> {
  rows: T[];
  /** Stable row identifier (used as React key + measureElement key). */
  rowKey: (row: T, index: number) => string;
  columns: VirtualTableColumn<T>[];
  /** Initial guess for row height — actual heights are measured. */
  estimatedRowHeight?: number;
  /** Max viewport height before scroll. Default lets the parent decide. */
  maxHeight?: number | string;
  /** Tighter row padding (use inside cards). */
  density?: "comfortable" | "compact";
  /** Optional click handler — adds keyboard activation for free. */
  onRowClick?: (row: T, index: number) => void;
  /** Shown when ``rows`` is empty. */
  emptyMessage?: ReactNode;
  /** Apply to the outer card. */
  className?: string;
}

const ALIGN_CLASS = {
  left: "justify-start text-left",
  right: "justify-end text-right",
  center: "justify-center text-center",
} as const;

export function VirtualTable<T>({
  rows,
  rowKey,
  columns,
  estimatedRowHeight = 44,
  maxHeight = 360,
  density = "comfortable",
  onRowClick,
  emptyMessage = "No rows",
  className,
}: VirtualTableProps<T>) {
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimatedRowHeight,
    overscan: 6,
    // Remeasure on each item — TanStack handles the ResizeObserver wiring
    // internally when ``measureElement`` is attached to each row.
  });

  // Recompute when row count changes so we don't keep stale offsets.
  useEffect(() => {
    virtualizer.measure();
  }, [rows.length, virtualizer]);

  const gridTemplate = columns.map((c) => c.width).join(" ");
  const rowVPadClass = density === "compact" ? "py-1.5" : "py-2.5";
  const headerPadClass = density === "compact" ? "py-1.5" : "py-2";

  if (rows.length === 0) {
    return (
      <div
        className={cn(
          "overflow-hidden rounded-xl border border-border bg-card",
          className
        )}
      >
        <HeaderRow
          columns={columns}
          gridTemplate={gridTemplate}
          headerPadClass={headerPadClass}
        />
        <div className="flex items-center justify-center px-3 py-8 text-xs text-muted-foreground">
          {emptyMessage}
        </div>
      </div>
    );
  }

  const virtualItems = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();

  return (
    <div
      role="grid"
      aria-rowcount={rows.length + 1}
      className={cn(
        "overflow-hidden rounded-xl border border-border bg-card",
        className
      )}
    >
      <HeaderRow
        columns={columns}
        gridTemplate={gridTemplate}
        headerPadClass={headerPadClass}
      />
      <div
        ref={parentRef}
        className="overflow-auto"
        style={{ maxHeight }}
      >
        <div
          style={{
            height: totalSize,
            position: "relative",
            width: "100%",
          }}
        >
          {virtualItems.map((vRow) => {
            const row = rows[vRow.index];
            const interactive = !!onRowClick;
            const rowStyle: CSSProperties = {
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              transform: `translateY(${vRow.start}px)`,
              display: "grid",
              gridTemplateColumns: gridTemplate,
              columnGap: "0.75rem",
              alignItems: "center",
            };
            return (
              <div
                key={rowKey(row, vRow.index)}
                ref={virtualizer.measureElement}
                data-index={vRow.index}
                role="row"
                aria-rowindex={vRow.index + 2}
                tabIndex={interactive ? 0 : -1}
                onClick={
                  interactive ? () => onRowClick(row, vRow.index) : undefined
                }
                onKeyDown={
                  interactive
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onRowClick(row, vRow.index);
                        }
                      }
                    : undefined
                }
                style={rowStyle}
                className={cn(
                  "group px-3 text-sm transition-colors",
                  rowVPadClass,
                  "border-b border-border/40 last:border-b-0",
                  interactive &&
                    "cursor-pointer hover:bg-accent/40 focus-visible:bg-accent/40 focus-visible:outline-none"
                )}
              >
                {columns.map((c) => (
                  <div
                    key={c.key}
                    role="gridcell"
                    className={cn(
                      "flex min-w-0 items-center",
                      ALIGN_CLASS[c.align ?? "left"],
                      c.cellClassName
                    )}
                  >
                    {c.cell(row)}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function HeaderRow<T>({
  columns,
  gridTemplate,
  headerPadClass,
}: {
  columns: VirtualTableColumn<T>[];
  gridTemplate: string;
  headerPadClass: string;
}) {
  return (
    <div
      role="row"
      style={{
        display: "grid",
        gridTemplateColumns: gridTemplate,
        columnGap: "0.75rem",
      }}
      className={cn(
        "border-b border-border bg-muted/40 px-3",
        "text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground",
        headerPadClass
      )}
    >
      {columns.map((c) => (
        <div
          key={c.key}
          role="columnheader"
          className={cn(
            "flex min-w-0 items-center",
            ALIGN_CLASS[c.align ?? "left"]
          )}
        >
          {c.header}
        </div>
      ))}
    </div>
  );
}
