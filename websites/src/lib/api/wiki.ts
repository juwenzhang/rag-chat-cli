import "server-only";

import { apiFetch } from "@/lib/api/client";
import type {
  WikiMemberOut,
  WikiOut,
  WikiPageDetailOut,
  WikiPageListOut,
  WikiPageShareOut,
  WikiPageSharePublicOut,
  WikiRole,
  WikiVisibility,
} from "@/lib/api/types";

// ── Wikis (knowledge bases) ─────────────────────────────────────────

export interface CreateWikiBody {
  name: string;
  slug?: string;
  description?: string;
  visibility?: WikiVisibility;
}

export interface UpdateWikiBody {
  name?: string;
  /** `null` clears the description; `undefined` leaves it untouched. */
  description?: string | null;
  visibility?: WikiVisibility;
}

export async function listWikis(
  token: string,
  orgId: string
): Promise<WikiOut[]> {
  return apiFetch<WikiOut[]>(`/orgs/${orgId}/wikis`, { token });
}

export async function createWiki(
  token: string,
  orgId: string,
  body: CreateWikiBody
): Promise<WikiOut> {
  return apiFetch<WikiOut>(`/orgs/${orgId}/wikis`, {
    method: "POST",
    token,
    body,
  });
}

export async function getWiki(
  token: string,
  wikiId: string
): Promise<WikiOut> {
  return apiFetch<WikiOut>(`/wikis/${wikiId}`, { token });
}

export async function updateWiki(
  token: string,
  wikiId: string,
  body: UpdateWikiBody
): Promise<WikiOut> {
  return apiFetch<WikiOut>(`/wikis/${wikiId}`, {
    method: "PATCH",
    token,
    body,
  });
}

export async function deleteWiki(token: string, wikiId: string): Promise<void> {
  await apiFetch<void>(`/wikis/${wikiId}`, { method: "DELETE", token });
}

// ── Wiki members ────────────────────────────────────────────────────

export interface AddWikiMemberBody {
  email: string;
  role?: WikiRole;
}

export interface UpdateWikiMemberRoleBody {
  role: WikiRole;
}

export async function listWikiMembers(
  token: string,
  wikiId: string
): Promise<WikiMemberOut[]> {
  return apiFetch<WikiMemberOut[]>(`/wikis/${wikiId}/members`, { token });
}

export async function addWikiMember(
  token: string,
  wikiId: string,
  body: AddWikiMemberBody
): Promise<WikiMemberOut> {
  return apiFetch<WikiMemberOut>(`/wikis/${wikiId}/members`, {
    method: "POST",
    token,
    body,
  });
}

export async function updateWikiMember(
  token: string,
  wikiId: string,
  userId: string,
  body: UpdateWikiMemberRoleBody
): Promise<WikiMemberOut> {
  return apiFetch<WikiMemberOut>(`/wikis/${wikiId}/members/${userId}`, {
    method: "PATCH",
    token,
    body,
  });
}

export async function removeWikiMember(
  token: string,
  wikiId: string,
  userId: string
): Promise<void> {
  await apiFetch<void>(`/wikis/${wikiId}/members/${userId}`, {
    method: "DELETE",
    token,
  });
}

// ── Wiki pages ──────────────────────────────────────────────────────

export interface CreateWikiPageBody {
  title?: string;
  parent_id?: string | null;
  body?: string;
}

export interface UpdateWikiPageBody {
  title?: string;
  body?: string;
  parent_id?: string | null;
  revision: number;
}

export interface MovePageBody {
  target_wiki_id?: string;
  new_parent_id?: string | null;
}

export async function listPages(
  token: string,
  wikiId: string
): Promise<WikiPageListOut[]> {
  return apiFetch<WikiPageListOut[]>(`/wikis/${wikiId}/pages`, { token });
}

export async function createPage(
  token: string,
  wikiId: string,
  body: CreateWikiPageBody
): Promise<WikiPageDetailOut> {
  return apiFetch<WikiPageDetailOut>(`/wikis/${wikiId}/pages`, {
    method: "POST",
    token,
    body,
  });
}

export async function getPage(
  token: string,
  pageId: string
): Promise<WikiPageDetailOut> {
  return apiFetch<WikiPageDetailOut>(`/wiki-pages/${pageId}`, { token });
}

export async function updatePage(
  token: string,
  pageId: string,
  body: UpdateWikiPageBody
): Promise<WikiPageDetailOut> {
  return apiFetch<WikiPageDetailOut>(`/wiki-pages/${pageId}`, {
    method: "PATCH",
    token,
    body,
  });
}

export async function deletePage(
  token: string,
  pageId: string
): Promise<void> {
  await apiFetch<void>(`/wiki-pages/${pageId}`, { method: "DELETE", token });
}

export async function duplicatePage(
  token: string,
  pageId: string
): Promise<WikiPageDetailOut> {
  return apiFetch<WikiPageDetailOut>(`/wiki-pages/${pageId}/duplicate`, {
    method: "POST",
    token,
  });
}

export async function movePage(
  token: string,
  pageId: string,
  body: MovePageBody
): Promise<WikiPageDetailOut> {
  return apiFetch<WikiPageDetailOut>(`/wiki-pages/${pageId}/move`, {
    method: "POST",
    token,
    body,
  });
}

// ── Wiki page shares ────────────────────────────────────────────────

export async function createPageShare(
  token: string,
  pageId: string
): Promise<WikiPageShareOut> {
  return apiFetch<WikiPageShareOut>(`/wiki-pages/${pageId}/share`, {
    method: "POST",
    token,
  });
}

export async function getPageShare(
  token: string,
  pageId: string
): Promise<WikiPageShareOut> {
  return apiFetch<WikiPageShareOut>(`/wiki-pages/${pageId}/share`, { token });
}

export async function revokePageShare(
  token: string,
  shareToken: string
): Promise<void> {
  await apiFetch<void>(`/wiki-page-shares/${shareToken}`, {
    method: "DELETE",
    token,
  });
}

/** Public — no Authorization header. */
export async function fetchPageSharePublic(
  shareToken: string
): Promise<WikiPageSharePublicOut> {
  return apiFetch<WikiPageSharePublicOut>(`/wiki-page-shares/${shareToken}`, {
    // token omitted on purpose — the route is public.
  });
}
