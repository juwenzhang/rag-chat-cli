import type { WikiPageListOut } from "@/lib/api/types";

export interface TreeNode {
  page: WikiPageListOut;
  children: TreeNode[];
}

/**
 * Build the page hierarchy from the flat server list. Siblings sort by
 * `position`, then most-recently-updated first as a tiebreaker.
 */
export function buildTree(pages: WikiPageListOut[]): TreeNode[] {
  const byId = new Map<string, TreeNode>();
  for (const p of pages) byId.set(p.id, { page: p, children: [] });
  const roots: TreeNode[] = [];
  for (const node of byId.values()) {
    const parentId = node.page.parent_id;
    if (parentId && byId.has(parentId)) {
      byId.get(parentId)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  const sort = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.page.position !== b.page.position) {
        return a.page.position - b.page.position;
      }
      return b.page.updated_at.localeCompare(a.page.updated_at);
    });
    for (const n of nodes) sort(n.children);
  };
  sort(roots);
  return roots;
}
