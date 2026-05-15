import "server-only";

import { apiFetch } from "@/lib/api/client";
import type { DocumentDetailOut, DocumentOut } from "@/lib/api/types";

export async function listDocuments(token: string): Promise<DocumentOut[]> {
  const data = await apiFetch<{ items: DocumentOut[] } | DocumentOut[]>(
    "/knowledge/documents",
    { token }
  );
  return Array.isArray(data) ? data : data.items;
}

export interface CreateDocumentBody {
  title?: string;
  body?: string;
  source?: string;
}

export interface UpdateDocumentBody {
  title?: string;
  body?: string;
}

export async function addDocument(
  token: string,
  body: CreateDocumentBody
): Promise<DocumentDetailOut> {
  return apiFetch<DocumentDetailOut>("/knowledge/documents", {
    method: "POST",
    token,
    body,
  });
}

export async function getDocument(
  token: string,
  documentId: string
): Promise<DocumentDetailOut> {
  return apiFetch<DocumentDetailOut>(`/knowledge/documents/${documentId}`, {
    token,
  });
}

export async function updateDocument(
  token: string,
  documentId: string,
  body: UpdateDocumentBody
): Promise<DocumentDetailOut> {
  return apiFetch<DocumentDetailOut>(`/knowledge/documents/${documentId}`, {
    method: "PATCH",
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
