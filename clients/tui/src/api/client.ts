import {clearTokens, loadTokens, saveTokens, type StoredTokens} from './token-store';
import {ApiError} from './types';
import type {
  MessageOut,
  SessionMeta,
  ThinkMode,
  TokenPair,
  UserOut
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

const DEFAULT_BASE_URL = 'http://127.0.0.1:8000';

export class ApiClient {
  readonly baseUrl: string;
  private tokens: StoredTokens | null;

  constructor(options: ApiClientOptions = {}) {
    const fromEnv = process.env['RAG_API_BASE_URL']?.trim();
    this.baseUrl = (options.baseUrl || fromEnv || DEFAULT_BASE_URL).replace(/\/+$/, '');
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
    body: {title?: string; pinned?: boolean; provider_id?: string; model?: string}
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
    const headers: Record<string, string> = {Accept: 'application/json'};
    if (init.body !== undefined) headers['Content-Type'] = 'application/json';

    const authed = init.authed !== false;
    if (authed && this.tokens) {
      headers['Authorization'] = `Bearer ${this.tokens.access_token}`;
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
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
      const response = await fetch(`${this.baseUrl}/auth/refresh`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', Accept: 'application/json'},
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
