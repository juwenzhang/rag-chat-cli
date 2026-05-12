import "server-only";

import { apiFetch } from "@/lib/api/client";
import type { DocumentOut, KnowledgeHit } from "@/lib/api/types";

export async function listDocuments(token: string): Promise<DocumentOut[]> {
  const data = await apiFetch<{ items: DocumentOut[] } | DocumentOut[]>(
    "/knowledge/documents",
    { token }
  );
  return Array.isArray(data) ? data : data.items;
}

export async function search(
  token: string,
  query: string,
  top_k = 5
): Promise<KnowledgeHit[]> {
  const data = await apiFetch<{ hits: KnowledgeHit[] } | KnowledgeHit[]>(
    "/knowledge/search",
    { token, query: { q: query, top_k } }
  );
  return Array.isArray(data) ? data : data.hits;
}

export async function addDocument(
  token: string,
  body: { title: string; content: string; source?: string }
): Promise<DocumentOut> {
  return apiFetch<DocumentOut>("/knowledge/documents", {
    method: "POST",
    token,
    body,
  });
}

export async function deleteDocument(
  token: string,
  documentId: string
): Promise<void> {
  await apiFetch<void>(`/knowledge/documents/${documentId}`, {
    method: "DELETE",
    token,
  });
}
