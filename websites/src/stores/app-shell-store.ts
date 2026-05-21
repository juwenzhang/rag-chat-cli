"use client";

import { create } from "zustand";

import type { OrgOut, UserOut } from "@/lib/api/shared/types";

interface AppShellStore {
  user: UserOut | null;
  orgs: OrgOut[];
  activeOrgId: string | null;
  initShell: (input: {
    user: UserOut;
    orgs: OrgOut[];
    activeOrgId: string | null;
  }) => void;
  setActiveOrgId: (orgId: string) => void;
  resetShell: () => void;
}

export const useAppShellStore = create<AppShellStore>((set) => ({
  user: null,
  orgs: [],
  activeOrgId: null,

  initShell: ({ user, orgs, activeOrgId }) =>
    set({ user, orgs, activeOrgId }),

  setActiveOrgId: (activeOrgId) => set({ activeOrgId }),

  resetShell: () => set({ user: null, orgs: [], activeOrgId: null }),
}));
