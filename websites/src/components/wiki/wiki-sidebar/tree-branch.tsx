"use client";

import { useState } from "react";

import type { WikiPageListOut } from "@/lib/api/types";

import { PageRow } from "./page-row";
import type { TreeNode } from "./tree";

/** Recursive page-tree node — renders a row plus its expandable children. */
export function TreeBranch({
  wikiId,
  node,
  depth,
  activePageId,
  canEdit,
  onAddChild,
  onRequestDelete,
}: {
  wikiId: string;
  node: TreeNode;
  depth: number;
  activePageId: string | null;
  canEdit: boolean;
  onAddChild: (parentId: string) => void;
  onRequestDelete: (page: WikiPageListOut) => void;
}) {
  const [open, setOpen] = useState(true);
  const hasChildren = node.children.length > 0;
  return (
    <li>
      <PageRow
        wikiId={wikiId}
        page={node.page}
        depth={depth}
        active={node.page.id === activePageId}
        canEdit={canEdit}
        expanded={hasChildren ? open : undefined}
        onToggleExpand={hasChildren ? () => setOpen((v) => !v) : undefined}
        onAddChild={() => onAddChild(node.page.id)}
        onRequestDelete={() => onRequestDelete(node.page)}
      />
      {hasChildren && open && (
        <ul className="flex flex-col gap-0.5">
          {node.children.map((c) => (
            <TreeBranch
              key={c.page.id}
              wikiId={wikiId}
              node={c}
              depth={depth + 1}
              activePageId={activePageId}
              canEdit={canEdit}
              onAddChild={onAddChild}
              onRequestDelete={onRequestDelete}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
