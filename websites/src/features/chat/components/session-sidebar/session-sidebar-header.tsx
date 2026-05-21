"use client";

import { ChevronsLeft, MessageSquarePlus, Search } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export function SessionSidebarHeader({
  creating,
  query,
  onCollapse,
  onCreate,
  onQueryChange,
}: {
  creating: boolean;
  query: string;
  onCollapse: () => void;
  onCreate: () => void;
  onQueryChange: (next: string) => void;
}) {
  return (
    <>
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <Link href="/chat" className="flex items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-md bg-brand-gradient text-white shadow shadow-primary/20">
            <span className="text-xs font-bold">R</span>
          </div>
          <span className="font-semibold tracking-tight">lhx-rag</span>
        </Link>
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={onCollapse}
                aria-label="Collapse sidebar"
              >
                <ChevronsLeft />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">Collapse</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <div className="p-3">
        <Button onClick={onCreate} disabled={creating} className="w-full">
          <MessageSquarePlus />
          {creating ? "Creating…" : "New conversation"}
        </Button>
      </div>

      <div className="relative px-3 pb-3">
        <Search className="absolute left-6 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Search conversations…"
          className="pl-9"
        />
      </div>
    </>
  );
}
