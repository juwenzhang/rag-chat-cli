"use client";

import { useEffect } from "react";

/**
 * First-visit system-preference detector.
 *
 * The server renders `<html class="dark">` only when there's already a
 * `theme` cookie. On a brand-new visitor we don't know the OS preference
 * from the server, so this client component checks `prefers-color-scheme`
 * once on mount and flips the class accordingly. Doesn't write a cookie —
 * we wait for the user to explicitly choose so subsequent renders are
 * deterministic from the cookie alone.
 *
 * Only mutates the DOM; never calls setState. No flash on subsequent
 * visits once the user has toggled at least once.
 */
export function ThemeBootstrap({ hasPreference }: { hasPreference: boolean }) {
  useEffect(() => {
    if (hasPreference) return;
    if (typeof window === "undefined") return;
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    if (prefersDark) {
      document.documentElement.classList.add("dark");
    }
  }, [hasPreference]);
  return null;
}
