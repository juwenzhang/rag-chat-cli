import { api } from "@/lib/api/browser";

export const bookmarkService = {
  createShare: (body: { user_message_id: string; assistant_message_id: string }) =>
    api.shares.create(body),

  deleteBookmark: (bookmarkId: string) => api.bookmarks.remove(bookmarkId),
};
