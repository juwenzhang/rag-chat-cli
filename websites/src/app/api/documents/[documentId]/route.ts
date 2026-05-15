import { knowledgeApi } from "@/lib/api";
import type { UpdateDocumentBody } from "@/lib/api/knowledge";

import { readJson, withAuth } from "../../_bff";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ documentId: string }> }
) {
  const { documentId } = await ctx.params;
  return withAuth((token) => knowledgeApi.getDocument(token, documentId));
}

export async function PATCH(
  req: Request,
  ctx: { params: Promise<{ documentId: string }> }
) {
  const { documentId } = await ctx.params;
  const body = await readJson<UpdateDocumentBody>(req);
  return withAuth((token) =>
    knowledgeApi.updateDocument(token, documentId, body)
  );
}

export async function DELETE(
  _req: Request,
  ctx: { params: Promise<{ documentId: string }> }
) {
  const { documentId } = await ctx.params;
  return withAuth(async (token) => {
    await knowledgeApi.deleteDocument(token, documentId);
    return { ok: true };
  });
}
