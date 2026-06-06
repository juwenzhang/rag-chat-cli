import { BookmarksPageClient } from "@/features/bookmarks/components/bookmarks-page-client";
import { bookmarkApi } from "@/lib/api";
import { requireUser } from "@/lib/auth/session.server";

export const dynamic = "force-dynamic";

export default async function BookmarksPage() {
  const { token, user } = await requireUser();
  const bookmarks = await bookmarkApi.listBookmarksFull(token).catch(() => []);
  return <BookmarksPageClient currentUserId={user.id} bookmarks={bookmarks} />;
}
