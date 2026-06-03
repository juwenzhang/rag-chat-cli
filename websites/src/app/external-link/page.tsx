import { AlertTriangle, ExternalLink } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { safeExternalTarget } from "@/lib/external-link";
import { getServerI18n } from "@/lib/i18n/server";

export const dynamic = "force-dynamic";

export default async function ExternalLinkPage({
  searchParams,
}: {
  searchParams: Promise<{ target?: string }>;
}) {
  const params = await searchParams;
  const { t } = await getServerI18n();
  const target = safeExternalTarget(params.target);
  const host = target ? new URL(target).host : null;

  return (
    <main className="flex min-h-dvh items-center justify-center bg-background px-4 py-10 text-foreground">
      <section className="w-full max-w-xl rounded-2xl border border-border bg-card p-6 shadow-xl">
        <div className="flex items-start gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-warning/15 text-warning">
            <AlertTriangle className="size-5" />
          </div>
          <div className="min-w-0 flex-1">
            <h1 className="text-lg font-semibold">{t("externalLink.title")}</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {t("externalLink.description")}
            </p>
          </div>
        </div>

        <div className="mt-5 rounded-xl border border-border bg-muted/40 p-3">
          <div className="text-xs font-medium text-muted-foreground">
            {t("externalLink.target")}
          </div>
          {target ? (
            <>
              <div className="mt-1 text-sm font-medium text-foreground">{host}</div>
              <p className="mt-1 break-all text-xs text-muted-foreground">{target}</p>
            </>
          ) : (
            <p className="mt-1 text-sm text-destructive">{t("externalLink.invalid")}</p>
          )}
        </div>

        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button asChild variant="outline">
            <Link href="/chat">{t("externalLink.back")}</Link>
          </Button>
          <Button asChild disabled={!target}>
            <a href={target ?? "#"} target="_blank" rel="noopener noreferrer">
              {t("externalLink.continue")}
              <ExternalLink className="size-4" />
            </a>
          </Button>
        </div>
      </section>
    </main>
  );
}
