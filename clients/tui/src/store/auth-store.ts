import {create} from 'zustand';

import type {ApiClient} from '../api/client';
import type {UserOut} from '../api/types';

interface AuthState {
  user: UserOut | null;
  bootstrapping: boolean;
  loginError: string | null;
  logging: boolean;
  bootstrap: (api: ApiClient) => Promise<void>;
  login: (api: ApiClient, email: string, password: string) => Promise<boolean>;
  logout: (api: ApiClient) => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  bootstrapping: true,
  loginError: null,
  logging: false,

  async bootstrap(api) {
    set({bootstrapping: true, loginError: null});
    if (!api.isAuthed()) {
      set({user: null, bootstrapping: false});
      return;
    }
    try {
      const user = await api.me();
      set({user, bootstrapping: false});
    } catch {
      set({user: null, bootstrapping: false});
    }
  },

  async login(api, email, password) {
    set({logging: true, loginError: null});
    try {
      const user = await api.login(email, password);
      set({user, logging: false, loginError: null});
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'login failed';
      set({logging: false, loginError: message});
      return false;
    }
  },

  async logout(api) {
    await api.logout();
    set({user: null, loginError: null});
  }
}));
