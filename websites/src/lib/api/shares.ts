import "server-only";

import { apiFetch } from "@/lib/api/client";
import type { SessionMeta, SharePublicOut, ShareOut } from "@/lib/api/types";

export interface CreateShareBody {
  user_message_id: string;
  assistant_message_id: string;
}

export async function createShare(
  token: string,
  body: CreateShareBody
): Promise<ShareOut> {
  return apiFetch<ShareOut>("/shares", {
    method: "POST",
    token,
    body,
  });
}

export async function listMyShares(token: string): Promise<ShareOut[]> {
  return apiFetch<ShareOut[]>("/shares", { token });
}

export async function revokeShare(
  token: string,
  shareToken: string
): Promise<void> {
  await apiFetch<void>(`/shares/${shareToken}`, {
    method: "DELETE",
    token,
  });
}

/** Public — no Authorization header. */
export async function fetchSharePublic(
  shareToken: string
): Promise<SharePublicOut> {
  return apiFetch<SharePublicOut>(`/shares/${shareToken}`, {
    // token omitted on purpose — the route is public.
  });
}

export async function forkFromShare(
  token: string,
  shareToken: string
): Promise<SessionMeta> {
  return apiFetch<SessionMeta>("/chat/sessions/from-share", {
    method: "POST",
    token,
    body: { token: shareToken },
  });
}
