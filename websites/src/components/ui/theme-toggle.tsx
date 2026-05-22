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

export function useIsDark(): boolean {
  return useSyncExternalStore(subscribe, getIsDark, getServerSnapshot);
}

export function ThemeToggle({
  ariaLabel = "Toggle theme",
  tooltip = "Toggle theme",
}: {
  ariaLabel?: string;
  tooltip?: string;
}) {
  const isDark = useIsDark();

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setTheme(!isDark)}
            aria-label={ariaLabel}
          >
            <Sun className="size-4 dark:hidden" />
            <Moon className="hidden size-4 dark:inline-block" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>{tooltip}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
