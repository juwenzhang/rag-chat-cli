import {create} from 'zustand';

import type {ApiClient} from '../api/client';
import type {SessionMeta} from '../api/types';

interface SessionState {
  sessions: SessionMeta[];
  activeId: string | null;
  loading: boolean;
  error: string | null;

  refresh: (api: ApiClient) => Promise<void>;
  select: (id: string) => void;
  create: (api: ApiClient, title?: string | null) => Promise<SessionMeta | null>;
  remove: (api: ApiClient, id: string) => Promise<void>;
  rename: (api: ApiClient, id: string, title: string) => Promise<void>;
  upsertLocal: (session: SessionMeta) => void;
  reset: () => void;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  activeId: null,
  loading: false,
  error: null,

  async refresh(api) {
    set({loading: true, error: null});
    try {
      const sessions = await api.listSessions();
      sessions.sort(
        (a, b) =>
          (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) ||
          Date.parse(b.updated_at || b.created_at) -
            Date.parse(a.updated_at || a.created_at)
      );
      const active = get().activeId;
      const stillThere = active && sessions.some((s) => s.id === active);
      const nextActive = stillThere ? active : sessions[0]?.id ?? null;
      set({sessions, activeId: nextActive, loading: false});
    } catch (error) {
      const message = error instanceof Error ? error.message : 'failed to load sessions';
      set({loading: false, error: message});
    }
  },

  select(id) {
    set({activeId: id});
  },

  async create(api, title) {
    try {
      const created = await api.createSession(title ?? null);
      set((state) => ({
        sessions: [created, ...state.sessions.filter((s) => s.id !== created.id)],
        activeId: created.id
      }));
      return created;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'failed to create session';
      set({error: message});
      return null;
    }
  },

  async remove(api, id) {
    try {
      await api.deleteSession(id);
      set((state) => {
        const sessions = state.sessions.filter((s) => s.id !== id);
        const activeId =
          state.activeId === id ? sessions[0]?.id ?? null : state.activeId;
        return {sessions, activeId};
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'failed to delete session';
      set({error: message});
    }
  },

  async rename(api, id, title) {
    try {
      const updated = await api.updateSession(id, {title});
      set((state) => ({
        sessions: state.sessions.map((s) => (s.id === id ? updated : s))
      }));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'failed to rename session';
      set({error: message});
    }
  },

  upsertLocal(session) {
    set((state) => {
      const exists = state.sessions.some((s) => s.id === session.id);
      const sessions = exists
        ? state.sessions.map((s) => (s.id === session.id ? session : s))
        : [session, ...state.sessions];
      return {sessions};
    });
  },

  reset() {
    set({sessions: [], activeId: null, error: null});
  }
}));
