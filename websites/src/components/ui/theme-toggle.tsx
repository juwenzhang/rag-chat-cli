"use client";

import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/**
 * SSR-safe theme toggle.
 *
 * Source of truth: the `dark` class on <html>. The server renders this
 * from a `theme` cookie (see `app/layout.tsx`), so there's no FOUC for
 * returning visitors. Toggling here:
 *   1. flips the class on <html>
 *   2. writes the cookie so subsequent SSR renders match
 *
 * We subscribe via `useSyncExternalStore` to a MutationObserver so the
 * icon stays in sync if anything else flips the theme.
 */
function getIsDark(): boolean {
  return document.documentElement.classList.contains("dark");
}

function getServerSnapshot(): boolean {
  return false;
}

function subscribe(cb: () => void): () => void {
  const observer = new MutationObserver(cb);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"],
  });
  return () => observer.disconnect();
}

const ONE_YEAR_S = 60 * 60 * 24 * 365;

export function setTheme(next: boolean) {
  document.documentElement.classList.toggle("dark", next);
  document.cookie = `theme=${next ? "dark" : "light"}; path=/; max-age=${ONE_YEAR_S}; samesite=lax`;
}

/** Subscribe to the live `dark`-class state on <html>. SSR-safe. */
export function useIsDark(): boolean {
  return useSyncExternalStore(subscribe, getIsDark, getServerSnapshot);
}

export function ThemeToggle() {
  const isDark = useIsDark();

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setTheme(!isDark)}
            aria-label="Toggle theme"
          >
            <Sun className="size-4 dark:hidden" />
            <Moon className="hidden size-4 dark:inline-block" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          Switch to {isDark ? "light" : "dark"} mode
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
