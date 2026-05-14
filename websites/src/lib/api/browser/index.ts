/**
 * Typed browser-side API surface — the one module Client Components import
 * to talk to the BFF. Every function is a thin, named wrapper over `bff` /
 * `bffStream` so call sites never hand-write URLs, methods, or `.json()`.
 *
 * Mirrors the Route Handlers under `src/app/api/**`. On failure the
 * underlying `bff` throws `ApiError` — callers `try/catch` (usually to
 * `toast.error(err.message)`); they never inspect HTTP status by hand.
 *
 * Request-body shapes are reused from the `server-only` `src/lib/api/*`
 * modules via `import type` (erased at compile time — no runtime import,
 * so the `server-only` guard is never tripped).
 */

import { bff, bffStream } from "@/lib/api/browser/client";
import type { CreateBookmarkBody } from "@/lib/api/bookmarks";
import type {
  ChatStreamParams,
  RegenerateStreamParams,
  UpdateSessionBody,
} from "@/lib/api/chat";
import type {
  AddMemberBody,
  CreateOrgBody,
  TransferOwnershipBody,
  UpdateMemberRoleBody,
  UpdateOrgBody,
} from "@/lib/api/orgs";
import type {
  ConnectivityTestBody,
  ProviderCreateBody,
  ProviderUpdateBody,
  RunningModel,
  UserPreferenceBody,
} from "@/lib/api/providers";
import type { CreateShareBody } from "@/lib/api/shares";
import type {
  AddWikiMemberBody,
  CreateWikiBody,
  CreateWikiPageBody,
  MovePageBody,
  UpdateWikiBody,
  UpdateWikiMemberRoleBody,
  UpdateWikiPageBody,
} from "@/lib/api/wiki";
import type {
  BookmarkDetailOut,
  BookmarkOut,
  ConnectivityTestOut,
  MemberOut,
  MessageOut,
  ModelListItem,
  OrgOut,
  ProviderOut,
  SessionMeta,
  ShareOut,
  SharePublicOut,
  UserPreferenceOut,
  WikiMemberOut,
  WikiOut,
  WikiPageDetailOut,
  WikiPageListOut,
} from "@/lib/api/types";

/** Result of an action-only route (`DELETE`, revoke, …). */
type Ok = { ok: boolean };

const chat = {
  listSessions: () => bff<SessionMeta[]>("/api/chat/sessions"),

  createSession: (title?: string) =>
    bff<SessionMeta>("/api/chat/sessions", {
      method: "POST",
      body: { title },
    }),

  updateSession: (sessionId: string, body: UpdateSessionBody) =>
    bff<SessionMeta>(`/api/chat/sessions/${sessionId}`, {
      method: "PATCH",
      body,
    }),

  deleteSession: (sessionId: string) =>
    bff<void>(`/api/chat/sessions/${sessionId}`, { method: "DELETE" }),

  getMessages: (sessionId: string) =>
    bff<MessageOut[]>(`/api/chat/sessions/${sessionId}/messages`),

  sessionFromShare: (token: string) =>
    bff<SessionMeta>("/api/chat/sessions/from-share", {
      method: "POST",
      body: { token },
    }),

  sessionFromWiki: (pageId: string) =>
    bff<SessionMeta>(`/api/chat/sessions/from-wiki/${pageId}`, {
      method: "POST",
    }),

  /** Open the SSE stream for a fresh turn. */
  stream: (body: ChatStreamParams, signal?: AbortSignal) =>
    bffStream("/api/chat/stream", { method: "POST", body, signal }),

  /** Open the SSE stream that re-runs the trailing assistant turn. */
  regenerate: (body: RegenerateStreamParams, signal?: AbortSignal) =>
    bffStream("/api/chat/stream/regenerate", {
      method: "POST",
      body,
      signal,
    }),
};

const providers = {
  list: () => bff<ProviderOut[]>("/api/providers"),

  create: (body: ProviderCreateBody) =>
    bff<ProviderOut>("/api/providers", { method: "POST", body }),

  update: (providerId: string, body: ProviderUpdateBody) =>
    bff<ProviderOut>(`/api/providers/${providerId}`, {
      method: "PATCH",
      body,
    }),

  remove: (providerId: string) =>
    bff<void>(`/api/providers/${providerId}`, { method: "DELETE" }),

  test: (body: ConnectivityTestBody) =>
    bff<ConnectivityTestOut>("/api/providers/test", {
      method: "POST",
      body,
    }),

  listModels: (providerId: string) =>
    bff<ModelListItem[]>(`/api/providers/${providerId}/models`),

  deleteModel: (providerId: string, model: string) =>
    bff<Ok>(`/api/providers/${providerId}/models/delete`, {
      method: "POST",
      body: { model },
    }),

  upsertModelMeta: (
    providerId: string,
    model: string,
    description: string | null
  ) =>
    bff<Ok>(`/api/providers/${providerId}/models/meta`, {
      method: "POST",
      body: { model, description },
    }),

  showModel: (providerId: string, model: string) =>
    bff<Record<string, unknown>>(`/api/providers/${providerId}/models/show`, {
      method: "POST",
      body: { model },
    }),

  listRunningModels: (providerId: string) =>
    bff<RunningModel[]>(`/api/providers/${providerId}/ps`),

  /** Open the SSE stream that reports `ollama pull` progress. */
  pullModel: (providerId: string, model: string, signal?: AbortSignal) =>
    bffStream(`/api/providers/${providerId}/models/pull`, {
      method: "POST",
      body: { model },
      signal,
    }),
};

const me = {
  getPreferences: () => bff<UserPreferenceOut>("/api/me/preferences"),

  updatePreferences: (body: UserPreferenceBody) =>
    bff<UserPreferenceOut>("/api/me/preferences", { method: "PUT", body }),
};

const orgs = {
  list: () => bff<OrgOut[]>("/api/orgs"),

  create: (body: CreateOrgBody) =>
    bff<OrgOut>("/api/orgs", { method: "POST", body }),

  get: (orgId: string) => bff<OrgOut>(`/api/orgs/${orgId}`),

  update: (orgId: string, body: UpdateOrgBody) =>
    bff<OrgOut>(`/api/orgs/${orgId}`, { method: "PATCH", body }),

  remove: (orgId: string) =>
    bff<void>(`/api/orgs/${orgId}`, { method: "DELETE" }),

  transferOwnership: (orgId: string, body: TransferOwnershipBody) =>
    bff<OrgOut>(`/api/orgs/${orgId}/transfer`, { method: "POST", body }),

  listMembers: (orgId: string) =>
    bff<MemberOut[]>(`/api/orgs/${orgId}/members`),

  addMember: (orgId: string, body: AddMemberBody) =>
    bff<MemberOut>(`/api/orgs/${orgId}/members`, { method: "POST", body }),

  updateMemberRole: (
    orgId: string,
    userId: string,
    body: UpdateMemberRoleBody
  ) =>
    bff<MemberOut>(`/api/orgs/${orgId}/members/${userId}`, {
      method: "PATCH",
      body,
    }),

  removeMember: (orgId: string, userId: string) =>
    bff<void>(`/api/orgs/${orgId}/members/${userId}`, { method: "DELETE" }),

  listWikis: (orgId: string) => bff<WikiOut[]>(`/api/orgs/${orgId}/wikis`),

  createWiki: (orgId: string, body: CreateWikiBody) =>
    bff<WikiOut>(`/api/orgs/${orgId}/wikis`, { method: "POST", body }),
};

const wikis = {
  get: (wikiId: string) => bff<WikiOut>(`/api/wikis/${wikiId}`),

  update: (wikiId: string, body: UpdateWikiBody) =>
    bff<WikiOut>(`/api/wikis/${wikiId}`, { method: "PATCH", body }),

  remove: (wikiId: string) =>
    bff<void>(`/api/wikis/${wikiId}`, { method: "DELETE" }),

  listMembers: (wikiId: string) =>
    bff<WikiMemberOut[]>(`/api/wikis/${wikiId}/members`),

  addMember: (wikiId: string, body: AddWikiMemberBody) =>
    bff<WikiMemberOut>(`/api/wikis/${wikiId}/members`, {
      method: "POST",
      body,
    }),

  updateMemberRole: (
    wikiId: string,
    userId: string,
    body: UpdateWikiMemberRoleBody
  ) =>
    bff<WikiMemberOut>(`/api/wikis/${wikiId}/members/${userId}`, {
      method: "PATCH",
      body,
    }),

  removeMember: (wikiId: string, userId: string) =>
    bff<void>(`/api/wikis/${wikiId}/members/${userId}`, { method: "DELETE" }),

  listPages: (wikiId: string) =>
    bff<WikiPageListOut[]>(`/api/wikis/${wikiId}/pages`),

  createPage: (wikiId: string, body: CreateWikiPageBody) =>
    bff<WikiPageDetailOut>(`/api/wikis/${wikiId}/pages`, {
      method: "POST",
      body,
    }),
};

const wikiPages = {
  get: (pageId: string) => bff<WikiPageDetailOut>(`/api/wiki-pages/${pageId}`),

  update: (pageId: string, body: UpdateWikiPageBody) =>
    bff<WikiPageDetailOut>(`/api/wiki-pages/${pageId}`, {
      method: "PATCH",
      body,
    }),

  remove: (pageId: string) =>
    bff<void>(`/api/wiki-pages/${pageId}`, { method: "DELETE" }),

  move: (pageId: string, body: MovePageBody) =>
    bff<WikiPageDetailOut>(`/api/wiki-pages/${pageId}/move`, {
      method: "POST",
      body,
    }),

  duplicate: (pageId: string) =>
    bff<WikiPageDetailOut>(`/api/wiki-pages/${pageId}/duplicate`, {
      method: "POST",
    }),
};

const bookmarks = {
  list: () => bff<BookmarkOut[]>("/api/bookmarks"),

  listFull: () => bff<BookmarkDetailOut[]>("/api/bookmarks/full"),

  create: (body: CreateBookmarkBody) =>
    bff<BookmarkOut>("/api/bookmarks", { method: "POST", body }),

  remove: (id: string) =>
    bff<void>(`/api/bookmarks/${id}`, { method: "DELETE" }),
};

const shares = {
  listMine: () => bff<ShareOut[]>("/api/shares"),

  create: (body: CreateShareBody) =>
    bff<ShareOut>("/api/shares", { method: "POST", body }),

  getPublic: (token: string) =>
    bff<SharePublicOut>(`/api/shares/${token}`),

  remove: (token: string) =>
    bff<void>(`/api/shares/${token}`, { method: "DELETE" }),
};

const activeOrg = {
  set: (orgId: string) =>
    bff<{ ok: boolean; org_id: string }>("/api/active-org", {
      method: "POST",
      body: { org_id: orgId },
    }),
};

const auth = {
  logout: () => bff<Ok>("/api/auth/logout", { method: "POST" }),
};

/**
 * The browser API namespace. Import as `import { api } from "@/lib/api/browser"`
 * and call `api.chat.listSessions()`, `api.providers.test(body)`, etc.
 */
export const api = {
  chat,
  providers,
  me,
  orgs,
  wikis,
  wikiPages,
  bookmarks,
  shares,
  activeOrg,
  auth,
};

export { bff, bffStream } from "@/lib/api/browser/client";
export type { BffRequestOptions } from "@/lib/api/browser/client";
