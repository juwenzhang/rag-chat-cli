import {clearTokens, loadTokens, saveTokens, type StoredTokens} from './token-store';
import {ApiError} from './types';
import type {
  ConnectivityTestOut,
  DocumentDetailOut,
  DocumentOut,
  MessageEvaluationOut,
  MessageOut,
  ModelListItem,
  Page,
  ProviderCreateIn,
  ProviderOut,
  ProviderUpdateIn,
  SearchHitOut,
  SessionMeta,
  ThinkMode,
  TokenPair,
  UserOut,
  UserPreferenceIn,
  UserPreferenceOut
} from './types';

/**
 * lhx-rag is API-only: every interaction goes through this thin wrapper around
 * the FastAPI backend. We keep the client deliberately small — auth, sessions,
 * messages and the streaming endpoints. Anything else lives behind the Web UI.
 */

export interface ApiClientOptions {
  baseUrl?: string;
}

interface RequestInitX {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  /** When false, never attach the bearer token (used for /auth/login). */
  authed?: boolean;
}

const FALLBACK_BASE_URL = 'http://127.0.0.1:8000';

/**
 * Path prefix and client identification shared by every request.
 *
 * `/v1/*` is the FastAPI sub-app dedicated to non-browser clients
 * (see ``docs/MULTI_CLIENT_AUTH_DESIGN.md``). It enforces an
 * ``X-Client-Id`` allowlist instead of an ``Origin`` allowlist so reverse
 * proxies that strip / refuse browser-flavoured headers (Hugging Face
 * Spaces, some CDNs) keep the CLI working.
 */
const API_PREFIX = '/v1';
const CLIENT_ID = 'lhx-rag-cli';
const USER_AGENT = `lhx-rag/${process.env['npm_package_version'] ?? '0.1.0'} (ink-tui)`;

/**
 * Resolve the FastAPI base URL with a single, well-known precedence chain:
 *
 *   1. explicit `options.baseUrl` (programmatic override, used in tests)
 *   2. `RAG_API_BASE_URL`         (per-invocation shell override)
 *   3. `DEFAULT_BASE_URL`         (set in `clients/tui/.env`, baked in at
 *                                  build time and re-loaded at dev runtime)
 *   4. `FALLBACK_BASE_URL`        (loopback, sensible default for local dev)
 */
function resolveBaseUrl(explicit?: string): string {
  const candidates = [
    explicit,
    process.env['RAG_API_BASE_URL'],
    process.env['DEFAULT_BASE_URL']
  ];
  for (const candidate of candidates) {
    const trimmed = candidate?.trim();
    if (trimmed) return trimmed.replace(/\/+$/, '');
  }
  return FALLBACK_BASE_URL;
}

export class ApiClient {
  readonly baseUrl: string;
  private tokens: StoredTokens | null;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = resolveBaseUrl(options.baseUrl);
    this.tokens = loadTokens();
  }

  isAuthed(): boolean {
    return this.tokens !== null;
  }

  currentEmail(): string | null {
    return this.tokens?.email ?? null;
  }

  /* ── auth ──────────────────────────────────────────────────────── */

  async login(email: string, password: string): Promise<UserOut> {
    const pair = await this.request<TokenPair>('/auth/login', {
      method: 'POST',
      body: {email, password},
      authed: false
    });
    this.tokens = saveTokens(pair, email);
    return this.me();
  }

  async register(email: string, password: string, displayName?: string): Promise<UserOut> {
    return this.request<UserOut>('/auth/register', {
      method: 'POST',
      body: {email, password, display_name: displayName ?? null},
      authed: false
    });
  }

  async me(): Promise<UserOut> {
    return this.request<UserOut>('/me');
  }

  async logout(): Promise<void> {
    const refresh = this.tokens?.refresh_token;
    clearTokens();
    this.tokens = null;
    if (!refresh) return;
    try {
      await this.requestRaw('/auth/logout', {
        method: 'POST',
        body: {refresh_token: refresh},
        authed: false
      });
    } catch {
      // logout is best-effort — local tokens are already gone
    }
  }

  /* ── sessions ──────────────────────────────────────────────────── */

  async listSessions(): Promise<SessionMeta[]> {
    const data = await this.request<{items: SessionMeta[]} | SessionMeta[]>(
      '/chat/sessions'
    );
    return Array.isArray(data) ? data : data.items;
  }

  async createSession(title?: string | null): Promise<SessionMeta> {
    return this.request<SessionMeta>('/chat/sessions', {
      method: 'POST',
      body: {title: title ?? null}
    });
  }

  async updateSession(
    sessionId: string,
    body: {
      title?: string;
      pinned?: boolean;
      provider_id?: string;
      model?: string;
      clear_provider_id?: boolean;
      clear_model?: boolean;
    }
  ): Promise<SessionMeta> {
    return this.request<SessionMeta>(`/chat/sessions/${sessionId}`, {
      method: 'PATCH',
      body
    });
  }

  async deleteSession(sessionId: string): Promise<void> {
    await this.request<void>(`/chat/sessions/${sessionId}`, {method: 'DELETE'});
  }

  async getMessages(sessionId: string): Promise<MessageOut[]> {
    const data = await this.request<{items: MessageOut[]} | MessageOut[]>(
      `/chat/sessions/${sessionId}/messages`
    );
    return Array.isArray(data) ? data : data.items;
  }

  /* ── streaming ─────────────────────────────────────────────────── */

  async openChatStream(
    body: {session_id: string; content: string; use_rag?: boolean; think?: ThinkMode | null},
    signal?: AbortSignal
  ): Promise<Response> {
    return this.requestRaw('/chat/stream', {method: 'POST', body, signal});
  }

  async openRegenerateStream(
    body: {session_id: string; use_rag?: boolean; think?: ThinkMode | null},
    signal?: AbortSignal
  ): Promise<Response> {
    return this.requestRaw('/chat/stream/regenerate', {method: 'POST', body, signal});
  }

  /* ── messages (edit / delete / evaluate) ───────────────────────── */

  async editMessage(messageId: string, content: string): Promise<MessageOut> {
    return this.request<MessageOut>(`/chat/messages/${messageId}`, {
      method: 'PATCH',
      body: {content}
    });
  }

  async deleteMessage(messageId: string): Promise<void> {
    await this.request<void>(`/chat/messages/${messageId}`, {method: 'DELETE'});
  }

  async getEvaluation(messageId: string): Promise<MessageEvaluationOut> {
    return this.request<MessageEvaluationOut>(
      `/chat/messages/${messageId}/evaluation`
    );
  }

  async evaluateMessage(messageId: string): Promise<MessageEvaluationOut> {
    return this.request<MessageEvaluationOut>(
      `/chat/messages/${messageId}/evaluation`,
      {method: 'POST'}
    );
  }

  /* ── knowledge ─────────────────────────────────────────────────── */

  async listDocuments(page = 1, size = 50): Promise<Page<DocumentOut>> {
    return this.request<Page<DocumentOut>>(
      `/knowledge/documents?page=${page}&size=${size}`
    );
  }

  async getDocument(documentId: string): Promise<DocumentDetailOut> {
    return this.request<DocumentDetailOut>(`/knowledge/documents/${documentId}`);
  }

  async createDocument(body: {
    title?: string;
    source?: string;
    body: string;
  }): Promise<DocumentDetailOut> {
    return this.request<DocumentDetailOut>('/knowledge/documents', {
      method: 'POST',
      body: {
        title: body.title ?? 'Untitled',
        source: body.source ?? 'cli-upload',
        body: body.body
      }
    });
  }

  async updateDocument(
    documentId: string,
    body: {title?: string; body?: string}
  ): Promise<DocumentDetailOut> {
    return this.request<DocumentDetailOut>(`/knowledge/documents/${documentId}`, {
      method: 'PATCH',
      body
    });
  }

  async deleteDocument(documentId: string): Promise<void> {
    await this.request<void>(`/knowledge/documents/${documentId}`, {
      method: 'DELETE'
    });
  }

  async reindexDocuments(): Promise<void> {
    await this.request<void>('/knowledge/documents:reindex', {method: 'POST'});
  }

  async searchKnowledge(q: string, topK = 4): Promise<SearchHitOut[]> {
    const qs = `q=${encodeURIComponent(q)}&top_k=${topK}`;
    return this.request<SearchHitOut[]>(`/knowledge/search?${qs}`);
  }

  /* ── providers / models / preferences ──────────────────────────── */

  async listProviders(): Promise<ProviderOut[]> {
    return this.request<ProviderOut[]>('/providers');
  }

  async createProvider(body: ProviderCreateIn): Promise<ProviderOut> {
    return this.request<ProviderOut>('/providers', {method: 'POST', body});
  }

  async updateProvider(providerId: string, body: ProviderUpdateIn): Promise<ProviderOut> {
    return this.request<ProviderOut>(`/providers/${providerId}`, {
      method: 'PATCH',
      body
    });
  }

  async deleteProvider(providerId: string): Promise<void> {
    await this.request<void>(`/providers/${providerId}`, {method: 'DELETE'});
  }

  async listProviderModels(providerId: string): Promise<ModelListItem[]> {
    return this.request<ModelListItem[]>(`/providers/${providerId}/models`);
  }

  async deleteProviderModel(providerId: string, model: string): Promise<void> {
    await this.request<void>(`/providers/${providerId}/models/delete`, {
      method: 'POST',
      body: {model}
    });
  }

  async testProvider(body: {
    type: 'ollama' | 'openai';
    base_url: string;
    api_key?: string | null;
  }): Promise<ConnectivityTestOut> {
    return this.request<ConnectivityTestOut>('/providers/test', {
      method: 'POST',
      body
    });
  }

  /**
   * Pull an Ollama model. Backend streams SSE — we expose the raw Response so
   * the caller can read progress frames.
   */
  async openModelPullStream(
    providerId: string,
    model: string,
    signal?: AbortSignal
  ): Promise<Response> {
    return this.requestRaw(`/providers/${providerId}/models/pull`, {
      method: 'POST',
      body: {model},
      signal
    });
  }

  async getPreferences(): Promise<UserPreferenceOut> {
    return this.request<UserPreferenceOut>('/me/preferences');
  }

  async putPreferences(body: UserPreferenceIn): Promise<UserPreferenceOut> {
    return this.request<UserPreferenceOut>('/me/preferences', {
      method: 'PUT',
      body
    });
  }

  /* ── transport ─────────────────────────────────────────────────── */

  private async request<T>(path: string, init: RequestInitX = {}): Promise<T> {
    const response = await this.requestRaw(path, init);
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    if (!text) return undefined as T;
    try {
      return JSON.parse(text) as T;
    } catch {
      throw new ApiError(response.status, 'PARSE', `Invalid JSON from ${path}`);
    }
  }

  private async requestRaw(path: string, init: RequestInitX = {}, retried = false): Promise<Response> {
    const headers: Record<string, string> = {
      Accept: 'application/json',
      // Required by the backend's ``/v1/*`` ClientIdMiddleware. Sending it
      // unconditionally is safe — paths outside ``/v1`` simply ignore the
      // header.
      'X-Client-Id': CLIENT_ID,
      // Reverse proxies often gate on UA. A stable, version-tagged UA both
      // helps debugging and keeps us out of "unknown bot" buckets.
      'User-Agent': USER_AGENT
    };
    if (init.body !== undefined) headers['Content-Type'] = 'application/json';

    const authed = init.authed !== false;
    if (authed && this.tokens) {
      headers['Authorization'] = `Bearer ${this.tokens.access_token}`;
    }

    const response = await fetch(`${this.baseUrl}${API_PREFIX}${path}`, {
      method: init.method ?? 'GET',
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: init.signal
    });

    if (response.status === 401 && authed && !retried && this.tokens) {
      const refreshed = await this.tryRefresh();
      if (refreshed) {
        return this.requestRaw(path, init, true);
      }
    }

    if (!response.ok) {
      let code = `HTTP_${response.status}`;
      let message = response.statusText || 'request failed';
      let details: unknown = undefined;
      try {
        const body = await response.json();
        if (body && typeof body === 'object') {
          details = body;
          if ('detail' in body) {
            message = String((body as {detail: unknown}).detail);
          } else if ('message' in body) {
            message = String((body as {message: unknown}).message);
          }
          if ('code' in body && typeof (body as {code?: unknown}).code === 'string') {
            code = (body as {code: string}).code;
          }
        }
      } catch {
        // body wasn't JSON; keep the status text
      }
      throw new ApiError(response.status, code, message, details);
    }

    return response;
  }

  private async tryRefresh(): Promise<boolean> {
    if (!this.tokens) return false;
    try {
      const response = await fetch(`${this.baseUrl}${API_PREFIX}/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'X-Client-Id': CLIENT_ID,
          'User-Agent': USER_AGENT
        },
        body: JSON.stringify({refresh_token: this.tokens.refresh_token})
      });
      if (!response.ok) {
        clearTokens();
        this.tokens = null;
        return false;
      }
      const pair = (await response.json()) as TokenPair;
      this.tokens = saveTokens(pair, this.tokens.email ?? null);
      return true;
    } catch {
      return false;
    }
  }
}
