import "server-only";

import { apiFetch } from "@/lib/api/client";
import type { BookmarkDetailOut, BookmarkOut } from "@/lib/api/types";

export interface CreateBookmarkBody {
  user_message_id: string;
  assistant_message_id: string;
  note?: string | null;
}

export async function createBookmark(
  token: string,
  body: CreateBookmarkBody
): Promise<BookmarkOut> {
  return apiFetch<BookmarkOut>("/bookmarks", {
    method: "POST",
    token,
    body,
  });
}

export async function listBookmarks(token: string): Promise<BookmarkOut[]> {
  return apiFetch<BookmarkOut[]>("/bookmarks", { token });
}

export async function listBookmarksFull(
  token: string
): Promise<BookmarkDetailOut[]> {
  return apiFetch<BookmarkDetailOut[]>("/bookmarks/full", { token });
}

export async function deleteBookmark(
  token: string,
  bookmarkId: string
): Promise<void> {
  await apiFetch<void>(`/bookmarks/${bookmarkId}`, {
    method: "DELETE",
    token,
  });
}
