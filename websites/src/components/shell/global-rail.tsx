"use client";

import {
  Bookmark,
  Boxes,
  Building2,
  Check,
  ChevronsUpDown,
  LogOut,
  MessageSquare,
  Moon,
  Pencil,
  Settings,
  Sun,
  User as UserIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTransition } from "react";
import { toast } from "sonner";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { setTheme, useIsDark } from "@/components/ui/theme-toggle";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { OrgOut, UserOut } from "@/lib/api/types";
import { cn, initials } from "@/lib/utils";

interface Props {
  user: UserOut;
  orgs: OrgOut[];
  activeOrgId: string | null;
}

/**
 * The 56-px-wide rail that's always docked to the left of the app.
 *
 * Lark / Feishu-style IA: this is the only navigation surface that
 * stays visible across modules. Each section (chat, wiki, …) renders
 * its own sidebar to the right of this rail inside its own route
 * group layout, so the conversation list isn't crammed alongside the
 * wiki editor anymore.
 */
export function GlobalRail({ user, orgs, activeOrgId }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const [loggingOut, startLogout] = useTransition();
  const isDark = useIsDark();
  const activeOrg = orgs.find((o) => o.id === activeOrgId) ?? orgs[0] ?? null;

  const items: Array<{
    href: string;
    label: string;
    icon: React.ReactNode;
    match: (p: string) => boolean;
  }> = [
    {
      href: "/chat",
      label: "Chat",
      icon: <MessageSquare className="size-5" />,
      match: (p) => p === "/chat" || p.startsWith("/chat/"),
    },
    {
      href: "/wiki",
      label: "Wiki",
      icon: <Pencil className="size-5" />,
      match: (p) => p === "/wiki" || p.startsWith("/wiki/"),
    },
    {
      href: "/bookmarks",
      label: "Bookmarks",
      icon: <Bookmark className="size-5" />,
      match: (p) => p.startsWith("/bookmarks"),
    },
    {
      href: "/orgs",
      label: "Workspaces",
      icon: <Building2 className="size-5" />,
      match: (p) => p.startsWith("/orgs"),
    },
    {
      href: "/settings/providers",
      label: "Models",
      icon: <Boxes className="size-5" />,
      match: (p) => p.startsWith("/settings"),
    },
  ];

  const switchOrg = async (orgId: string) => {
    if (orgId === activeOrg?.id) return;
    const res = await fetch("/api/active-org", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ org_id: orgId }),
    });
    if (!res.ok) {
      toast.error("Failed to switch workspace");
      return;
    }
    // Route the URL too — a bare reload would keep us on
    // ``/wiki/{stale_page_id}`` if the user was viewing a page that
    // belongs to the *previous* workspace. Land on the module's index
    // for the new workspace instead, so the sidebar and content stay
    // consistent. Other modules (orgs, settings) aren't scope-bound to
    // a workspace, so they don't need redirection.
    if (pathname.startsWith("/wiki")) {
      window.location.href = "/wiki";
    } else if (pathname.startsWith("/chat") && pathname !== "/chat") {
      // Chat sessions are user-scoped (not workspace-scoped) but the
      // sidebar's session list still needs to refetch. A hard nav to
      // /chat keeps things simple.
      window.location.href = "/chat";
    } else {
      window.location.reload();
    }
  };

  const logout = () =>
    startLogout(async () => {
      await fetch("/api/auth/logout", { method: "POST" });
      toast.success("Signed out");
      router.push("/login");
      router.refresh();
    });

  return (
    <aside className="flex h-full w-14 shrink-0 flex-col items-center border-r border-border bg-card/40 py-3">
      {/* Brand */}
      <Link
        href="/chat"
        className="mb-3 flex size-9 items-center justify-center rounded-lg bg-brand-gradient text-white shadow shadow-primary/20"
      >
        <span className="text-sm font-bold">R</span>
      </Link>

      {/* Workspace switcher (compact — just initial letter) */}
      {activeOrg && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="mb-3 flex size-9 items-center justify-center rounded-lg border border-border bg-card text-xs font-semibold uppercase text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
              aria-label={`Active workspace: ${activeOrg.name}`}
              title={activeOrg.name}
            >
              {activeOrg.name.slice(0, 2)}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="right" align="start" className="w-64">
            <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {orgs.map((o) => (
              <DropdownMenuItem
                key={o.id}
                onSelect={(e) => {
                  e.preventDefault();
                  void switchOrg(o.id);
                }}
                className="flex items-center gap-2"
              >
                <Building2 className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="flex-1 truncate">{o.name}</span>
                {o.id === activeOrg.id && (
                  <Check className="size-3.5 text-primary" />
                )}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link href="/orgs">
                <ChevronsUpDown className="size-3.5" />
                Manage workspaces
              </Link>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      {/* Nav icons */}
      <TooltipProvider delayDuration={200}>
        <nav className="flex flex-1 flex-col items-center gap-1">
          {items.map((it) => {
            const active = it.match(pathname);
            return (
              <Tooltip key={it.href}>
                <TooltipTrigger asChild>
                  <Button
                    asChild
                    variant="ghost"
                    size="icon"
                    aria-label={it.label}
                    className={cn(
                      "size-10 rounded-lg text-muted-foreground",
                      active &&
                        "bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
                    )}
                  >
                    <Link href={it.href}>{it.icon}</Link>
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right">{it.label}</TooltipContent>
              </Tooltip>
            );
          })}
        </nav>

        {/* Account */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label="Account"
              className="rounded-full transition-transform hover:scale-105"
            >
              <Avatar className="size-9">
                <AvatarFallback className="bg-brand-gradient text-white text-xs">
                  {initials(user.display_name ?? user.email)}
                </AvatarFallback>
              </Avatar>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="right" align="end" className="w-56">
            <DropdownMenuLabel>
              <div className="flex flex-col">
                <span className="text-sm font-medium text-foreground">
                  {user.display_name || "Account"}
                </span>
                <span className="text-xs text-muted-foreground">
                  {user.email}
                </span>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled>
              <UserIcon />
              Profile
            </DropdownMenuItem>
            <DropdownMenuItem disabled>
              <Settings />
              Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={(e) => {
                e.preventDefault();
                setTheme(!isDark);
              }}
            >
              {isDark ? <Sun /> : <Moon />}
              Switch to {isDark ? "light" : "dark"} mode
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={logout} disabled={loggingOut}>
              <LogOut />
              {loggingOut ? "Signing out…" : "Sign out"}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </TooltipProvider>
    </aside>
  );
}
