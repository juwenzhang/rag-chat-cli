import type { Metadata } from "next";
import { cookies } from "next/headers";
import { Toaster } from "sonner";

import { ThemeBootstrap } from "@/components/ui/theme-bootstrap";

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

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Server-render the theme class from a cookie. No <script> in the
  // tree, so React 19 has nothing to complain about. ThemeToggle writes
  // this cookie; ThemeBootstrap (client) hydrates system preference on
  // the very first visit when no cookie exists yet.
  const themeCookie = (await cookies()).get("theme")?.value;
  const isDark = themeCookie === "dark";

  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={["h-full", isDark ? "dark" : ""].filter(Boolean).join(" ")}
    >
      <body className="min-h-full bg-background font-sans text-foreground antialiased">
        <ThemeBootstrap hasPreference={Boolean(themeCookie)} />
        {children}
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
