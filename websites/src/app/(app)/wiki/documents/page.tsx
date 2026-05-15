import { redirect } from "next/navigation";

import { DocumentTableClient } from "@/components/wiki/document-table-client";
import { knowledgeApi } from "@/lib/api";
import { getAccessToken, getCurrentUser } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function DocumentLibraryPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  const token = await getAccessToken();
  if (!token) redirect("/login");

  const documents = await knowledgeApi.listDocuments(token);

  return (
    <div className="mx-auto w-full max-w-4xl px-4 pb-16 pt-6 sm:px-8 sm:pt-10">
      <DocumentTableClient documents={documents} />
    </div>
  );
}
