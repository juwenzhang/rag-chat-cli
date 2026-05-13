import { redirect } from "next/navigation";

import { bookmarkApi } from "@/lib/api";
import { getAccessToken, getCurrentUser } from "@/lib/session";

import { BookmarksPageClient } from "./bookmarks-page-client";

export const dynamic = "force-dynamic";

export default async function BookmarksPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/api/auth/clear-and-login");
  const token = await getAccessToken();
  if (!token) redirect("/api/auth/clear-and-login");

  const bookmarks = await bookmarkApi.listBookmarksFull(token).catch(() => []);
  return <BookmarksPageClient currentUserId={user.id} bookmarks={bookmarks} />;
}
