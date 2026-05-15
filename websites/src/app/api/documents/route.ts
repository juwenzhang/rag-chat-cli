import { knowledgeApi } from "@/lib/api";
import type { CreateDocumentBody } from "@/lib/api/knowledge";

import { readJson, withAuth } from "../_bff";

export async function GET() {
  return withAuth((token) => knowledgeApi.listDocuments(token));
}

export async function POST(req: Request) {
  const body = await readJson<CreateDocumentBody>(req);
  return withAuth((token) => knowledgeApi.addDocument(token, body));
}
