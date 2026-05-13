import { bookmarkApi } from "@/lib/api";
import type { CreateBookmarkBody } from "@/lib/api/bookmarks";

import { readJson, withAuth } from "../_bff";

export async function GET() {
  return withAuth((token) => bookmarkApi.listBookmarks(token));
}

export async function POST(req: Request) {
  const body = await readJson<CreateBookmarkBody>(req);
  return withAuth((token) => bookmarkApi.createBookmark(token, body));
}
