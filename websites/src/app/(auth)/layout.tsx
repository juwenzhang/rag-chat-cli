import Link from "next/link";

import { LanguageToggle } from "@/components/shell/language-toggle";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { getServerI18n } from "@/lib/i18n/server";

export default async function AuthLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const { t } = await getServerI18n();

  return (
    <div className="relative flex min-h-screen w-full flex-col overflow-hidden">
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-brand-gradient opacity-[0.08] animate-gradient dark:opacity-[0.18]"
      />
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-dot-pattern opacity-[0.5] dark:opacity-[0.35]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -left-32 top-12 -z-10 h-72 w-72 rounded-full bg-brand-from/30 blur-[100px] animate-float"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -right-32 bottom-12 -z-10 h-80 w-80 rounded-full bg-brand-to/30 blur-[120px] animate-float [animation-delay:-3s]"
      />

      <header className="flex items-center justify-between p-6">
        <Link
          href="/"
          className="flex items-center gap-2 text-sm font-semibold tracking-tight"
        >
          <div className="flex size-8 items-center justify-center rounded-lg bg-brand-gradient text-white shadow-lg shadow-primary/20">
            <span className="font-bold">R</span>
          </div>
          <span>lhx-rag</span>
        </Link>
        <div className="flex items-center gap-1">
          <LanguageToggle />
          <ThemeToggle ariaLabel={t("theme.toggle")} tooltip={t("theme.toggle")} />
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-4 pb-12">
        <div className="w-full max-w-md">{children}</div>
      </main>

      <footer className="px-6 py-4 text-center text-xs text-muted-foreground">
        <p>
          Open source ·{" "}
          <a
            href="https://github.com/juwenzhang/rag-chat-cli"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-foreground hover:underline"
          >
            GitHub
          </a>{" "}
          · MIT License
        </p>
      </footer>
    </div>
  );
}
