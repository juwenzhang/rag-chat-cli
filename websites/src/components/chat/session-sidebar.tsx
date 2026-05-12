"use client";

import {
  ChevronsLeft,
  ChevronsRight,
  LogOut,
  MessageSquarePlus,
  Search,
  Settings,
  User,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import { toast } from "sonner";

import {
  Avatar,
  AvatarFallback,
} from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { SessionMeta, UserOut } from "@/lib/api/types";
import { cn, formatRelative, initials } from "@/lib/utils";

interface Props {
  user: UserOut;
  sessions: SessionMeta[];
}

function activeSessionId(pathname: string): string | null {
  const m = pathname.match(/^\/chat\/([^/]+)/);
  return m ? m[1] : null;
}

export function SessionSidebar({ user, sessions }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const currentId = activeSessionId(pathname);
  const [creating, startCreating] = useTransition();
  const [loggingOut, startLogout] = useTransition();
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState(false);

  const filtered = useMemo(() => {
    if (!query.trim()) return sessions;
    const q = query.toLowerCase();
    return sessions.filter((s) =>
      (s.title ?? "Untitled").toLowerCase().includes(q)
    );
  }, [sessions, query]);

  const createNew = () =>
    startCreating(async () => {
      const res = await fetch("/api/chat/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        toast.error("Failed to create conversation");
        return;
      }
      const meta = (await res.json()) as SessionMeta;
      router.push(`/chat/${meta.id}`);
      router.refresh();
    });

  const logout = () =>
    startLogout(async () => {
      await fetch("/api/auth/logout", { method: "POST" });
      toast.success("Signed out");
      router.push("/login");
      router.refresh();
    });

  if (collapsed) {
    return (
      <aside className="flex h-full w-14 shrink-0 flex-col border-r border-border bg-card/50">
        <div className="flex flex-col items-center gap-1 p-2">
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setCollapsed(false)}
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
                  onClick={createNew}
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
        <div className="p-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Account">
                <Avatar className="size-7">
                  <AvatarFallback className="bg-brand-gradient text-white text-[10px]">
                    {initials(user.display_name ?? user.email)}
                  </AvatarFallback>
                </Avatar>
              </Button>
            </DropdownMenuTrigger>
            <AccountMenuContent
              user={user}
              logout={logout}
              loggingOut={loggingOut}
            />
          </DropdownMenu>
        </div>
      </aside>
    );
  }

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-border bg-card/40">
      {/* Brand */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <Link href="/chat" className="flex items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-md bg-brand-gradient text-white shadow shadow-primary/20">
            <span className="text-xs font-bold">R</span>
          </div>
          <span className="font-semibold tracking-tight">RAG-AI</span>
        </Link>
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setCollapsed(true)}
                aria-label="Collapse sidebar"
              >
                <ChevronsLeft />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">Collapse</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      {/* New conversation */}
      <div className="p-3">
        <Button
          onClick={createNew}
          disabled={creating}
          className="w-full"
        >
          <MessageSquarePlus />
          {creating ? "Creating…" : "New conversation"}
        </Button>
      </div>

      {/* Search */}
      <div className="relative px-3 pb-3">
        <Search className="absolute left-6 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search conversations…"
          className="pl-9"
        />
      </div>

      {/* Sessions */}
      <ScrollArea className="flex-1 px-2 pb-2">
        {filtered.length === 0 ? (
          <p className="px-3 py-8 text-center text-xs text-muted-foreground">
            {query ? "No matches" : "No conversations yet"}
          </p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {filtered.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => router.push(`/chat/${s.id}`)}
                  className={cn(
                    "group w-full rounded-md px-3 py-2 text-left text-sm transition-all",
                    "hover:bg-accent/60",
                    s.id === currentId &&
                      "bg-accent text-accent-foreground shadow-sm"
                  )}
                >
                  <div
                    className={cn(
                      "truncate font-medium",
                      s.id === currentId
                        ? "text-foreground"
                        : "text-foreground/85"
                    )}
                  >
                    {s.title || "Untitled"}
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    {formatRelative(s.updated_at)}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </ScrollArea>

      {/* Footer / Account */}
      <div className="border-t border-border p-3">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex w-full items-center gap-3 rounded-md p-2 transition-colors hover:bg-accent"
            >
              <Avatar className="size-8">
                <AvatarFallback className="bg-brand-gradient text-white text-xs">
                  {initials(user.display_name ?? user.email)}
                </AvatarFallback>
              </Avatar>
              <div className="min-w-0 flex-1 text-left">
                <div className="truncate text-sm font-medium">
                  {user.display_name || user.email.split("@")[0]}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {user.email}
                </div>
              </div>
            </button>
          </DropdownMenuTrigger>
          <AccountMenuContent
            user={user}
            logout={logout}
            loggingOut={loggingOut}
          />
        </DropdownMenu>
      </div>
    </aside>
  );
}

function AccountMenuContent({
  user,
  logout,
  loggingOut,
}: {
  user: UserOut;
  logout: () => void;
  loggingOut: boolean;
}) {
  return (
    <DropdownMenuContent align="end" className="w-56">
      <DropdownMenuLabel>
        <div className="flex flex-col">
          <span className="text-sm font-medium text-foreground">
            {user.display_name || "Account"}
          </span>
          <span className="text-xs text-muted-foreground">{user.email}</span>
        </div>
      </DropdownMenuLabel>
      <DropdownMenuSeparator />
      <DropdownMenuItem disabled>
        <User />
        Profile
      </DropdownMenuItem>
      <DropdownMenuItem disabled>
        <Settings />
        Settings
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem onClick={logout} disabled={loggingOut}>
        <LogOut />
        {loggingOut ? "Signing out…" : "Sign out"}
      </DropdownMenuItem>
    </DropdownMenuContent>
  );
}
