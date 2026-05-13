import { bookmarkApi } from "@/lib/api";

import { withAuth } from "../../_bff";

export async function DELETE(
  _req: Request,
  ctx: { params: Promise<{ id: string }> }
) {
  const { id } = await ctx.params;
  return withAuth(async (token) => {
    await bookmarkApi.deleteBookmark(token, id);
    return { ok: true };
  });
}
