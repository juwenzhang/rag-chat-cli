import { redirect } from "next/navigation";

import { DocumentEditorClient } from "@/components/wiki/document-editor-client";
import { knowledgeApi } from "@/lib/api";
import { ApiError } from "@/lib/api/types";
import { getAccessToken, getCurrentUser } from "@/lib/session";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ documentId: string }>;
}

export default async function DocumentEditorPage({ params }: Props) {
  const { documentId } = await params;
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  const token = await getAccessToken();
  if (!token) redirect("/login");

  let doc;
  try {
    doc = await knowledgeApi.getDocument(token, documentId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      redirect("/wiki/documents");
    }
    throw err;
  }

  return <DocumentEditorClient key={doc.id} document={doc} />;
}
