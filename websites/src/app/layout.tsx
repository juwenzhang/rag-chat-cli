import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import { Toaster } from "sonner";
import { Analytics } from "@vercel/analytics/next";

import { LOCALE_COOKIE, resolveLocale } from "@/lib/i18n/messages";
import { I18nProvider } from "@/lib/i18n/provider";

import "./globals.css";

// Pre-hydration theme resolver. Emitted as the very first child of
// ``<head>`` so the browser executes it **synchronously** before
// painting any styled content. The browser only blocks paint on
// inline scripts when they run before the first style sheet is
// applied, which is exactly what happens here because Next.js
// emits ``globals.css`` *after* this <script> in the document order.
//
//   1. ``theme`` cookie set      → SSR already wrote class="dark" or not,
//                                   the script becomes a no-op.
//   2. No cookie + dark OS pref  → flip ``<html>`` to dark inline.
//   3. No cookie + light OS pref → leave it.
//
// We must use a plain inline ``<script>`` (not ``next/script``) because
// ``next/script`` strategies rely on the React runtime, which is
// exactly what we're trying to run *before*. ``beforeInteractive``
// also gets hoisted by Next's loader and is not guaranteed to be the
// first child of ``<head>``.
const THEME_BOOTSTRAP_SCRIPT = `(function(){try{var c=document.cookie.split('; ').find(function(x){return x.indexOf('theme=')===0});if(c){return}if(window.matchMedia('(prefers-color-scheme: dark)').matches){var h=document.documentElement;h.classList.add('dark');h.style.backgroundColor='oklch(0.18 0.008 12)';h.style.colorScheme='dark'}}catch(e){}})();`;

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
  // Server-render the theme class from a cookie when one exists. The
  // ``<script>`` injected via ``next/script`` (below) covers the
  // first-visit case synchronously — system-preference users never
  // see a light→dark flash because the script runs before paint and
  // toggles the class on ``<html>`` directly.
  const cookieStore = await cookies();
  const themeCookie = cookieStore.get("theme")?.value;
  const locale = resolveLocale(cookieStore.get(LOCALE_COOKIE)?.value);
  const isDark = themeCookie === "dark";

  // Inline style on ``<html>`` paints the correct background colour
  // immediately, even before ``globals.css`` has finished loading
  // and the ``--background`` CSS variable resolves. Without this,
  // the browser shows the default white (UA stylesheet) for the
  // tens of milliseconds between document parse and stylesheet
  // commit — exactly the "white flash before dark" the user reports.
  // The values are hand-extracted from globals.css's ``--background``
  // tokens to match.
  const inlineHtmlStyle = isDark
    ? { backgroundColor: "oklch(0.18 0.008 12)", colorScheme: "dark" as const }
    : { backgroundColor: "oklch(0.985 0.004 12)", colorScheme: "light" as const };

  return (
    <html
      lang={locale}
      suppressHydrationWarning
      className={["h-full", isDark ? "dark" : ""].filter(Boolean).join(" ")}
      style={inlineHtmlStyle}
    >
      <head>
        {/* Synchronously resolves system colour-scheme before React
            renders so first-visit users don't see a light → dark flash.
            Must be a plain inline ``<script>`` so it executes BEFORE
            the stylesheet below — that's what makes the run truly
            blocking-paint. Subsequent visits already have the cookie
            so the body is a no-op. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP_SCRIPT }} />
      </head>
      <body className="min-h-full bg-background font-sans text-foreground antialiased">
        <I18nProvider initialLocale={locale}>{children}</I18nProvider>
        <Toaster
          position="bottom-right"
          toastOptions={{
            classNames: {
              toast: "border-border bg-popover text-popover-foreground",
            },
          }}
        />
        <Analytics />
      </body>
    </html>
  );
}
