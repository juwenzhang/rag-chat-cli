"use client";

import { ChevronsRight, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export function CollapsedSidebar({
  canCreatePage,
  creating,
  onCreatePage,
  onExpand,
}: {
  canCreatePage: boolean;
  creating: boolean;
  onCreatePage: () => void;
  onExpand: () => void;
}) {
  return (
    <aside className="flex h-full w-12 shrink-0 flex-col items-center border-r border-border bg-card/40 py-2">
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={onExpand}
              aria-label="Expand sidebar"
            >
              <ChevronsRight />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">Expand</TooltipContent>
        </Tooltip>
        {canCreatePage && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={onCreatePage}
                disabled={creating}
                aria-label="New page"
                className="mt-1"
              >
                <Plus />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">New page</TooltipContent>
          </Tooltip>
        )}
      </TooltipProvider>
    </aside>
  );
}
