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

import { bff, bffForm, bffStream } from "@/lib/api/browser/client";
import type { CreateBookmarkBody } from "@/lib/api/server/bookmarks";
import type {
  ChatStreamParams,
  RegenerateStreamParams,
  UpdateSessionBody,
} from "@/lib/api/server/chat";
import type {
  AddMemberBody,
  CreateOrgBody,
  TransferOwnershipBody,
  UpdateMemberRoleBody,
  UpdateOrgBody,
} from "@/lib/api/server/orgs";
import type {
  ConnectivityTestBody,
  ProviderCreateBody,
  ProviderUpdateBody,
  RunningModel,
  UserPreferenceBody,
} from "@/lib/api/server/providers";
import type { CreateDocumentBody, UpdateDocumentBody } from "@/lib/api/server/knowledge";
import type { CreateShareBody } from "@/lib/api/server/shares";
import type {
  AddWikiMemberBody,
  CreateWikiBody,
  CreateWikiPageBody,
  MovePageBody,
  UpdateWikiBody,
  UpdateWikiMemberRoleBody,
  UpdateWikiPageBody,
} from "@/lib/api/server/wiki";
import type {
  AssetOut,
  BookmarkDetailOut,
  BookmarkOut,
  ConnectivityTestOut,
  DocumentDetailOut,
  DocumentOut,
  MemberOut,
  MessageEvaluationOut,
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
  WikiPageShareOut,
  WikiPageSharePublicOut,
} from "@/lib/api/shared/types";

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

  getMessageEvaluation: (messageId: string) =>
    bff<MessageEvaluationOut>(`/api/chat/messages/${messageId}/evaluation`),

  evaluateMessage: (messageId: string) =>
    bff<MessageEvaluationOut>(`/api/chat/messages/${messageId}/evaluation`, {
      method: "POST",
    }),

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

  upsertModelMeta: (providerId: string, model: string, description: string | null) =>
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

  create: (body: CreateOrgBody) => bff<OrgOut>("/api/orgs", { method: "POST", body }),

  get: (orgId: string) => bff<OrgOut>(`/api/orgs/${orgId}`),

  update: (orgId: string, body: UpdateOrgBody) =>
    bff<OrgOut>(`/api/orgs/${orgId}`, { method: "PATCH", body }),

  remove: (orgId: string) => bff<void>(`/api/orgs/${orgId}`, { method: "DELETE" }),

  transferOwnership: (orgId: string, body: TransferOwnershipBody) =>
    bff<OrgOut>(`/api/orgs/${orgId}/transfer`, { method: "POST", body }),

  listMembers: (orgId: string) => bff<MemberOut[]>(`/api/orgs/${orgId}/members`),

  addMember: (orgId: string, body: AddMemberBody) =>
    bff<MemberOut>(`/api/orgs/${orgId}/members`, { method: "POST", body }),

  updateMemberRole: (orgId: string, userId: string, body: UpdateMemberRoleBody) =>
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

  remove: (wikiId: string) => bff<void>(`/api/wikis/${wikiId}`, { method: "DELETE" }),

  listMembers: (wikiId: string) => bff<WikiMemberOut[]>(`/api/wikis/${wikiId}/members`),

  addMember: (wikiId: string, body: AddWikiMemberBody) =>
    bff<WikiMemberOut>(`/api/wikis/${wikiId}/members`, {
      method: "POST",
      body,
    }),

  updateMemberRole: (wikiId: string, userId: string, body: UpdateWikiMemberRoleBody) =>
    bff<WikiMemberOut>(`/api/wikis/${wikiId}/members/${userId}`, {
      method: "PATCH",
      body,
    }),

  removeMember: (wikiId: string, userId: string) =>
    bff<void>(`/api/wikis/${wikiId}/members/${userId}`, { method: "DELETE" }),

  listPages: (wikiId: string) => bff<WikiPageListOut[]>(`/api/wikis/${wikiId}/pages`),

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

  createShare: (pageId: string) =>
    bff<WikiPageShareOut>(`/api/wiki-pages/${pageId}/share`, {
      method: "POST",
    }),

  getShare: (pageId: string) => bff<WikiPageShareOut>(`/api/wiki-pages/${pageId}/share`),
};

const bookmarks = {
  list: () => bff<BookmarkOut[]>("/api/bookmarks"),

  listFull: () => bff<BookmarkDetailOut[]>("/api/bookmarks/full"),

  create: (body: CreateBookmarkBody) =>
    bff<BookmarkOut>("/api/bookmarks", { method: "POST", body }),

  remove: (id: string) => bff<void>(`/api/bookmarks/${id}`, { method: "DELETE" }),
};

const wikiPageShares = {
  getPublic: (token: string) =>
    bff<WikiPageSharePublicOut>(`/api/wiki-page-shares/${token}`),

  remove: (token: string) =>
    bff<void>(`/api/wiki-page-shares/${token}`, { method: "DELETE" }),
};

const shares = {
  listMine: () => bff<ShareOut[]>("/api/shares"),

  create: (body: CreateShareBody) =>
    bff<ShareOut>("/api/shares", { method: "POST", body }),

  getPublic: (token: string) => bff<SharePublicOut>(`/api/shares/${token}`),

  remove: (token: string) => bff<void>(`/api/shares/${token}`, { method: "DELETE" }),
};

/**
 * Files smaller than this go through the single-shot multipart endpoint
 * (one round trip, simplest path). Anything bigger is split into chunks
 * so a flaky network only retries the failed slice instead of the whole
 * blob, and so the BFF/FastAPI hop never has to buffer a fat request.
 */
const SINGLE_SHOT_LIMIT = 1.5 * 1024 * 1024;
const DEFAULT_CHUNK_SIZE = 512 * 1024;
const MAX_PARALLEL_CHUNKS = 3;

export interface UploadProgress {
  /** 0..1 — bytes acknowledged by the server / total bytes. */
  ratio: number;
  loaded: number;
  total: number;
}

export interface UploadImageOptions {
  signal?: AbortSignal;
  onProgress?: (p: UploadProgress) => void;
  /** Override the auto-chosen strategy; mostly for tests. */
  forceChunked?: boolean;
}

interface UploadCreateOut {
  status: "ready" | "completed";
  upload_id?: string | null;
  chunk_size?: number | null;
  expected_chunks?: number | null;
  received_chunks?: number[] | null;
  asset?: AssetOut | null;
}

interface UploadCompleteOut {
  status: "completed";
  asset: AssetOut;
}

async function sha256Hex(buffer: ArrayBuffer): Promise<string | null> {
  // crypto.subtle is unavailable in old browsers and on http origins; in
  // those cases we just skip the dedupe shortcut rather than blowing up.
  if (typeof crypto === "undefined" || !crypto.subtle) return null;
  try {
    const digest = await crypto.subtle.digest("SHA-256", buffer);
    return Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  } catch {
    return null;
  }
}

async function uploadImageSingleShot(
  file: File,
  opts: UploadImageOptions
): Promise<AssetOut> {
  const form = new FormData();
  form.set("file", file);
  opts.onProgress?.({ ratio: 0, loaded: 0, total: file.size });
  const asset = await bffForm<AssetOut>("/api/assets/images", form, {
    signal: opts.signal,
  });
  opts.onProgress?.({ ratio: 1, loaded: file.size, total: file.size });
  return asset;
}

async function uploadImageChunked(
  file: File,
  opts: UploadImageOptions
): Promise<AssetOut> {
  const buffer = await file.arrayBuffer();
  const sourceHash = await sha256Hex(buffer);

  const created = await bff<UploadCreateOut>("/api/assets/uploads", {
    method: "POST",
    body: {
      filename: file.name || "image",
      content_type: file.type || "application/octet-stream",
      total_size: file.size,
      source_hash: sourceHash,
      chunk_size: DEFAULT_CHUNK_SIZE,
    },
    signal: opts.signal,
  });

  // Server-side dedupe hit — no bytes need to leave the browser.
  if (created.status === "completed" && created.asset) {
    opts.onProgress?.({ ratio: 1, loaded: file.size, total: file.size });
    return created.asset;
  }
  if (!created.upload_id || !created.chunk_size || !created.expected_chunks) {
    throw new Error("upload session response is missing fields");
  }

  const uploadId = created.upload_id;
  const chunkSize = created.chunk_size;
  const expected = created.expected_chunks;

  let acknowledged = 0;
  const ack = (n: number) => {
    acknowledged += n;
    opts.onProgress?.({
      ratio: Math.min(1, acknowledged / file.size),
      loaded: Math.min(file.size, acknowledged),
      total: file.size,
    });
  };

  // Bound concurrency so we don't open too many parallel sockets on the
  // user's network stack — the wins flatten out fast past 3 streams.
  const queue = Array.from({ length: expected }, (_, i) => i);
  const workers: Promise<void>[] = [];
  let aborted: unknown = null;
  const upload = async () => {
    while (queue.length > 0 && !aborted) {
      const index = queue.shift();
      if (index === undefined) return;
      const start = index * chunkSize;
      const end = Math.min(start + chunkSize, file.size);
      const slice = buffer.slice(start, end);
      try {
        const res = await fetch(
          `/api/assets/uploads/${encodeURIComponent(uploadId)}/chunks/${index}`,
          {
            method: "PUT",
            body: slice,
            headers: { "Content-Type": "application/octet-stream" },
            credentials: "same-origin",
            cache: "no-store",
            signal: opts.signal,
          }
        );
        if (!res.ok) {
          const text = await res.text().catch(() => "");
          throw new Error(`chunk ${index} failed: ${res.status} ${text}`);
        }
        ack(end - start);
      } catch (err) {
        aborted = err;
        throw err;
      }
    }
  };
  for (let i = 0; i < Math.min(MAX_PARALLEL_CHUNKS, expected); i += 1) {
    workers.push(upload());
  }

  try {
    await Promise.all(workers);
  } catch (err) {
    // Best-effort cleanup; don't mask the original failure.
    void fetch(`/api/assets/uploads/${encodeURIComponent(uploadId)}`, {
      method: "DELETE",
      credentials: "same-origin",
      cache: "no-store",
    }).catch(() => undefined);
    throw err;
  }

  const completed = await bff<UploadCompleteOut>(
    `/api/assets/uploads/${encodeURIComponent(uploadId)}/complete`,
    { method: "POST", signal: opts.signal }
  );
  opts.onProgress?.({ ratio: 1, loaded: file.size, total: file.size });
  return completed.asset;
}

const assets = {
  uploadImage: (file: File, options: UploadImageOptions = {}) => {
    const useChunked = options.forceChunked || file.size > SINGLE_SHOT_LIMIT;
    return useChunked
      ? uploadImageChunked(file, options)
      : uploadImageSingleShot(file, options);
  },
};

const documents = {
  list: () => bff<DocumentOut[]>("/api/documents"),

  create: (body: CreateDocumentBody) =>
    bff<DocumentDetailOut>("/api/documents", { method: "POST", body }),

  get: (documentId: string) => bff<DocumentDetailOut>(`/api/documents/${documentId}`),

  update: (documentId: string, body: UpdateDocumentBody) =>
    bff<DocumentDetailOut>(`/api/documents/${documentId}`, {
      method: "PATCH",
      body,
    }),

  remove: (documentId: string) =>
    bff<void>(`/api/documents/${documentId}`, { method: "DELETE" }),
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
  wikiPageShares,
  bookmarks,
  shares,
  assets,
  documents,
  activeOrg,
  auth,
};

export { bff, bffForm, bffStream } from "@/lib/api/browser/client";
export type { BffRequestOptions } from "@/lib/api/browser/client";
