import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import { Toaster } from "sonner";

import { ThemeBootstrap } from "@/components/ui/theme-bootstrap";
import { LOCALE_COOKIE, resolveLocale } from "@/lib/i18n/messages";
import { I18nProvider } from "@/lib/i18n/provider";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "lhx-rag — Local ReAct agent with hybrid retrieval",
    template: "%s · lhx-rag",
  },
  description:
    "A local-first ReAct agent with hybrid RAG, persistent memory, and a streaming chat UI.",
  icons: { icon: "/favicon.ico" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Server-render the theme class from a cookie. No <script> in the
  // tree, so React 19 has nothing to complain about. ThemeToggle writes
  // this cookie; ThemeBootstrap (client) hydrates system preference on
  // the very first visit when no cookie exists yet.
  const cookieStore = await cookies();
  const themeCookie = cookieStore.get("theme")?.value;
  const locale = resolveLocale(cookieStore.get(LOCALE_COOKIE)?.value);
  const isDark = themeCookie === "dark";

  return (
    <html
      lang={locale}
      suppressHydrationWarning
      className={["h-full", isDark ? "dark" : ""].filter(Boolean).join(" ")}
    >
      <body className="min-h-full bg-background font-sans text-foreground antialiased">
        <I18nProvider initialLocale={locale}>
          <ThemeBootstrap hasPreference={Boolean(themeCookie)} />
          {children}
        </I18nProvider>
        <Toaster
          position="bottom-right"
          toastOptions={{
            classNames: {
              toast: "border-border bg-popover text-popover-foreground",
            },
          }}
        />
      </body>
    </html>
  );
}
