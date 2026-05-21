"use client";

import { create } from "zustand";

interface WikiStore {
  sidebarQuery: string;
  sidebarCollapsed: boolean;
  pageTitleOverrides: Record<string, string>;
  documentTitleOverrides: Record<string, string>;
  setSidebarQuery: (query: string) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setPageTitleOverride: (pageId: string, title: string) => void;
  setDocumentTitleOverride: (documentId: string, title: string) => void;
  clearPageTitleOverride: (pageId: string) => void;
  clearDocumentTitleOverride: (documentId: string) => void;
}

export const useWikiStore = create<WikiStore>((set) => ({
  sidebarQuery: "",
  sidebarCollapsed: false,
  pageTitleOverrides: {},
  documentTitleOverrides: {},

  setSidebarQuery: (sidebarQuery) => set({ sidebarQuery }),
  setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),

  setPageTitleOverride: (pageId, title) =>
    set((state) => ({
      pageTitleOverrides: { ...state.pageTitleOverrides, [pageId]: title },
    })),

  setDocumentTitleOverride: (documentId, title) =>
    set((state) => ({
      documentTitleOverrides: {
        ...state.documentTitleOverrides,
        [documentId]: title,
      },
    })),

  clearPageTitleOverride: (pageId) =>
    set((state) => {
      const next = { ...state.pageTitleOverrides };
      delete next[pageId];
      return { pageTitleOverrides: next };
    }),

  clearDocumentTitleOverride: (documentId) =>
    set((state) => {
      const next = { ...state.documentTitleOverrides };
      delete next[documentId];
      return { documentTitleOverrides: next };
    }),
}));
