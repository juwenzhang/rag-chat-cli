"use client";

import { create } from "zustand";

import type { ProviderOut, UserPreferenceOut } from "@/lib/api/shared/types";

interface ProvidersStore {
  providers: ProviderOut[];
  preferences: UserPreferenceOut;
  adding: boolean;
  init: (input: { providers: ProviderOut[]; preferences: UserPreferenceOut }) => void;
  setProviders: (providers: ProviderOut[]) => void;
  setPreferences: (preferences: UserPreferenceOut) => void;
  setAdding: (adding: boolean) => void;
}

export const useProvidersStore = create<ProvidersStore>((set) => ({
  providers: [],
  preferences: {
    default_provider_id: null,
    default_model: null,
    default_embedding_model: null,
    default_use_rag: false,
  },
  adding: false,

  init: ({ providers, preferences }) =>
    set({ providers, preferences, adding: providers.length === 0 }),

  setProviders: (providers) => set({ providers }),
  setPreferences: (preferences) => set({ preferences }),
  setAdding: (adding) => set({ adding }),
}));
