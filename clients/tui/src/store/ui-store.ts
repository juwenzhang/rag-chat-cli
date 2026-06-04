import {create} from 'zustand';

export type Pane = 'sessions' | 'transcript' | 'composer';
export type Overlay = 'help' | null;

export const PANE_ORDER: Pane[] = ['sessions', 'transcript', 'composer'];
export const PANE_LABEL: Record<Pane, string> = {
  sessions: 'sessions',
  transcript: 'transcript',
  composer: 'composer'
};

export interface Toast {
  id: string;
  level: 'info' | 'warn' | 'error' | 'ok';
  message: string;
}

interface UIState {
  pane: Pane;
  overlay: Overlay;
  status: string;
  followBottom: boolean;
  scrollOffset: number;
  toasts: Toast[];
  /** True while the composer's slash-command palette is showing candidates. */
  commandPaletteOpen: boolean;

  setPane: (pane: Pane) => void;
  cyclePane: (direction: 1 | -1) => void;
  setOverlay: (overlay: Overlay) => void;
  setStatus: (status: string) => void;
  setFollowBottom: (value: boolean) => void;
  setScrollOffset: (value: number) => void;
  setCommandPaletteOpen: (value: boolean) => void;
  pushToast: (level: Toast['level'], message: string) => void;
  dismissToast: (id: string) => void;
}

let toastSeq = 0;

export const useUiStore = create<UIState>((set) => ({
  pane: 'composer',
  overlay: null,
  status: 'ready',
  followBottom: true,
  scrollOffset: 0,
  toasts: [],
  commandPaletteOpen: false,

  setPane(pane) {
    set({pane});
  },

  cyclePane(direction) {
    set((state) => {
      const idx = PANE_ORDER.indexOf(state.pane);
      const len = PANE_ORDER.length;
      const nextIdx = (idx + direction + len) % len;
      return {pane: PANE_ORDER[nextIdx] ?? state.pane};
    });
  },

  setOverlay(overlay) {
    set({overlay});
  },

  setStatus(status) {
    set({status});
  },

  setFollowBottom(value) {
    if (value) set({followBottom: true, scrollOffset: 0});
    else set({followBottom: false});
  },

  setScrollOffset(value) {
    const next = Math.max(0, value);
    set({scrollOffset: next, followBottom: next === 0});
  },

  setCommandPaletteOpen(value) {
    set({commandPaletteOpen: value});
  },

  pushToast(level, message) {
    const id = `t${++toastSeq}`;
    set((state) => ({toasts: [...state.toasts, {id, level, message}]}));
    setTimeout(() => {
      set((state) => ({toasts: state.toasts.filter((t) => t.id !== id)}));
    }, level === 'error' ? 6000 : 3500);
  },

  dismissToast(id) {
    set((state) => ({toasts: state.toasts.filter((t) => t.id !== id)}));
  }
}));
