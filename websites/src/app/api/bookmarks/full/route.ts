import { bookmarkApi } from "@/lib/api";

import { withAuth } from "../../_bff";

export async function GET() {
  return withAuth((token) => bookmarkApi.listBookmarksFull(token));
}
