import {create} from 'zustand';

import type {ApiClient} from '../api/client';
import type {ProviderOut} from '../api/types';

/**
 * Lightweight provider cache. The sidebar footer + /model preview want
 * provider *names* (not opaque UUIDs) and don't want to refetch on every
 * keystroke. We keep a single in-memory list, refreshed on demand and
 * coalesced through ``loading`` so concurrent callers share one fetch.
 *
 * Cache TTL is 60s — providers change rarely (creating one is a manual
 * `/providers add`) and a stale name in a footer is harmless for that
 * window. Anything mutating providers should call ``invalidate()`` to
 * force a re-fetch on the next read.
 */
interface ProviderState {
  providers: ProviderOut[];
  loading: boolean;
  fetchedAt: number;
  /** Ensure ``providers`` is no older than ``ttlMs``. */
  ensureLoaded: (api: ApiClient, ttlMs?: number) => Promise<void>;
  /** Force a refresh on the next ``ensureLoaded`` call. */
  invalidate: () => void;
}

let inflight: Promise<void> | null = null;

export const useProviderStore = create<ProviderState>((set, get) => ({
  providers: [],
  loading: false,
  fetchedAt: 0,

  async ensureLoaded(api, ttlMs = 60_000) {
    const state = get();
    if (state.loading) {
      // Coalesce — let the in-flight call complete and serve the result.
      if (inflight) await inflight;
      return;
    }
    if (state.providers.length > 0 && Date.now() - state.fetchedAt < ttlMs) {
      return;
    }
    set({loading: true});
    inflight = (async () => {
      try {
        const list = await api.listProviders();
        set({providers: list, fetchedAt: Date.now(), loading: false});
      } catch {
        // Swallow — the footer reads ``providers`` directly and just shows
        // the id prefix when this fails. We don't want a transient 401 /
        // network blip to bubble up as a toast every minute.
        set({loading: false});
      } finally {
        inflight = null;
      }
    })();
    await inflight;
  },

  invalidate() {
    set({fetchedAt: 0});
  }
}));
