"use client";

import {
  Bookmark,
  Building2,
  Check,
  ChevronsUpDown,
  LogOut,
  Menu,
  MessageSquare,
  Moon,
  Pencil,
  Settings,
  Sun,
  User as UserIcon,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { toast } from "sonner";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { LanguageToggle } from "@/components/shell/language-toggle";
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
import { api } from "@/lib/api/browser";
import type { OrgOut, UserOut } from "@/lib/api/shared/types";
import { useI18n } from "@/lib/i18n/provider";
import { cn, initials } from "@/lib/utils";
import { useAppShellStore } from "@/stores/app-shell-store";

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
  const [mobileOpen, setMobileOpen] = useState(false);
  const isDark = useIsDark();
  const { t } = useI18n();
  const shellUser = useAppShellStore((state) => state.user) ?? user;
  const shellOrgs = useAppShellStore((state) => state.orgs);
  const shellActiveOrgId = useAppShellStore((state) => state.activeOrgId);
  const initShell = useAppShellStore((state) => state.initShell);
  const setActiveOrgId = useAppShellStore((state) => state.setActiveOrgId);
  const resetShell = useAppShellStore((state) => state.resetShell);
  const resolvedOrgs = shellOrgs.length > 0 ? shellOrgs : orgs;
  const resolvedActiveOrgId = shellActiveOrgId ?? activeOrgId;
  const activeOrg =
    resolvedOrgs.find((o) => o.id === resolvedActiveOrgId) ??
    resolvedOrgs[0] ??
    null;

  useEffect(() => {
    initShell({ user, orgs, activeOrgId });
  }, [activeOrgId, initShell, orgs, user]);

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
      label: t("nav.wiki"),
      icon: <Pencil className="size-5" />,
      match: (p) => p === "/wiki" || p.startsWith("/wiki/"),
    },
    {
      href: "/bookmarks",
      label: t("nav.bookmarks"),
      icon: <Bookmark className="size-5" />,
      match: (p) => p.startsWith("/bookmarks"),
    },
    {
      href: "/orgs",
      label: t("nav.workspaces"),
      icon: <Building2 className="size-5" />,
      match: (p) => p.startsWith("/orgs"),
    },
    {
      href: "/settings/account",
      label: t("nav.settings"),
      icon: <Settings className="size-5" />,
      match: (p) => p.startsWith("/settings"),
    },
  ];

  const switchOrg = async (orgId: string) => {
    if (orgId === activeOrg?.id) return;
    try {
      await api.activeOrg.set(orgId);
    } catch {
      toast.error("Failed to switch workspace");
      return;
    }
    setActiveOrgId(orgId);
    // Route the URL too — otherwise a stale wiki/page URL could point at
    // content from the previous workspace. Module index routes re-run the
    // server layouts and hydrate the stores with the new workspace data.
    if (pathname.startsWith("/wiki")) {
      router.push("/wiki");
    } else if (pathname.startsWith("/chat") && pathname !== "/chat") {
      router.push("/chat");
    }
    router.refresh();
  };

  const logout = () =>
    startLogout(async () => {
      try {
        await api.auth.logout();
      } catch {
        // Best-effort: even if revocation fails, fall through to /login —
        // the cookie is cleared server-side and a stale token is harmless.
      }
      resetShell();
      toast.success(t("nav.signedOut"));
      router.push("/login");
      router.refresh();
    });

  return (
    <>
      <Button
        variant="outline"
        size="icon"
        className="fixed left-3 top-[calc(0.75rem+env(safe-area-inset-top))] z-40 rounded-xl bg-background/90 shadow-sm backdrop-blur md:hidden"
        onClick={() => setMobileOpen(true)}
        aria-label={t("nav.open")}
      >
        <Menu />
      </Button>

      {mobileOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[1px] md:hidden"
          onClick={() => setMobileOpen(false)}
          aria-label={t("nav.close")}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] shrink-0 flex-col border-r border-border bg-card/95 px-3 py-4 shadow-2xl backdrop-blur transition-transform duration-200 md:static md:h-full md:w-14 md:max-w-none md:translate-x-0 md:items-center md:bg-card/40 md:px-0 md:py-3 md:shadow-none",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        )}
      >
        {activeOrg && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="mb-4 flex h-10 w-full items-center gap-2 rounded-lg border border-border bg-background px-3 text-left text-xs font-semibold uppercase text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground md:mb-3 md:size-9 md:justify-center md:px-0"
                aria-label={t("nav.activeWorkspace", { name: activeOrg.name })}
                title={activeOrg.name}
              >
                <span>{activeOrg.name.slice(0, 2)}</span>
                <span className="min-w-0 flex-1 truncate text-sm normal-case text-foreground md:hidden">
                  {activeOrg.name}
                </span>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="right" align="start" className="w-64">
              <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {resolvedOrgs.map((o) => (
                <DropdownMenuItem
                  key={o.id}
                  onSelect={(e) => {
                    e.preventDefault();
                    void switchOrg(o.id);
                    setMobileOpen(false);
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
                <Link href="/orgs" onClick={() => setMobileOpen(false)}>
                  <ChevronsUpDown className="size-3.5" />
                  {t("nav.manageWorkspaces")}
                </Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        <div className="mb-4 flex w-full items-center justify-between md:mb-3 md:block md:w-auto">
          <Link
            href="/chat"
            className="flex h-11 w-full items-center justify-start gap-3 rounded-xl px-3 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground md:size-10 md:justify-center md:px-0"
            onClick={() => setMobileOpen(false)}
          >
            <span className="flex size-5 items-center justify-center text-sm font-semibold">
              R
            </span>
            <span className="text-sm font-medium md:hidden">lhx-rag</span>
          </Link>
          <Button
            variant="ghost"
            size="icon-sm"
            className="md:hidden"
            onClick={() => setMobileOpen(false)}
            aria-label={t("nav.close")}
          >
            <X />
          </Button>
        </div>

        <TooltipProvider delayDuration={200}>
          <nav className="flex w-full min-w-0 flex-1 flex-col gap-1 md:w-auto md:items-center">
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
                        "h-11 w-full justify-start rounded-xl px-3 text-muted-foreground md:size-10 md:justify-center md:px-0",
                        active &&
                          "bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
                      )}
                    >
                      <Link href={it.href} onClick={() => setMobileOpen(false)}>
                        {it.icon}
                        <span className="md:hidden">{it.label}</span>
                      </Link>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="right">{it.label}</TooltipContent>
                </Tooltip>
              );
            })}
          </nav>

          <div className="mb-2 md:mb-3">
            <LanguageToggle />
          </div>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label={t("nav.account")}
                className="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left transition-colors hover:bg-accent md:w-auto md:rounded-full md:p-0 md:hover:scale-105 md:hover:bg-transparent"
              >
                <Avatar className="size-9">
                  <AvatarFallback className="bg-brand-gradient text-white text-xs">
                    {initials(shellUser.display_name ?? shellUser.email)}
                  </AvatarFallback>
                </Avatar>
                <span className="min-w-0 flex-1 md:hidden">
                  <span className="block truncate text-sm font-medium text-foreground">
                    {shellUser.display_name || t("nav.account")}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {shellUser.email}
                  </span>
                </span>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="right" align="end" className="w-56">
              <DropdownMenuLabel>
                <div className="flex flex-col">
                  <span className="text-sm font-medium text-foreground">
                    {shellUser.display_name || t("nav.account")}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {shellUser.email}
                  </span>
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem disabled>
                <UserIcon />
                {t("nav.profile")}
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
                {t("nav.switchTheme", {
                  mode: isDark ? t("common.light") : t("common.dark"),
                })}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={logout} disabled={loggingOut}>
                <LogOut />
                {loggingOut ? t("nav.signingOut") : t("nav.signOut")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </TooltipProvider>
      </aside>
    </>
  );
}
