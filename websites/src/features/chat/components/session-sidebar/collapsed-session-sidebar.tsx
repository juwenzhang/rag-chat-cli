"use client";

import { ChevronsRight, MessageSquarePlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export function CollapsedSessionSidebar({
  creating,
  onCreate,
  onExpand,
}: {
  creating: boolean;
  onCreate: () => void;
  onExpand: () => void;
}) {
  return (
    <aside className="hidden h-full w-14 shrink-0 flex-col border-r border-border bg-card/50 md:flex">
      <div className="flex flex-col items-center gap-1 p-2">
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={onExpand}
                aria-label="Expand sidebar"
              >
                <ChevronsRight />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">Expand</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={onCreate}
                disabled={creating}
                aria-label="New conversation"
              >
                <MessageSquarePlus />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">New conversation</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
      <div className="flex-1" />
    </aside>
  );
}
