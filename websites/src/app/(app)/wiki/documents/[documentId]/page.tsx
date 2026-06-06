import { redirect } from "next/navigation";

import { DocumentEditorClient } from "@/features/wiki/components/document-editor-client";
import { knowledgeApi } from "@/lib/api";
import { ApiError } from "@/lib/api/shared/types";
import { requireAccessToken } from "@/lib/auth/session.server";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ documentId: string }>;
}

export default async function DocumentEditorPage({ params }: Props) {
  const { documentId } = await params;
  const token = await requireAccessToken();

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
