import { Book, Lock, Plus } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Button } from "@/components/ui/button";
import { DocumentTableClient } from "@/features/wiki/components/document-table-client";
import { knowledgeApi, orgApi, wikiApi } from "@/lib/api";
import { requireAccessToken } from "@/lib/auth/session.server";
import { getServerI18n } from "@/lib/i18n/server";
import { resolveActiveOrg } from "@/lib/org/active-org.server";
import { cn, formatRelative } from "@/lib/utils";

export const dynamic = "force-dynamic";

/**
 * /wiki — workspace's wiki list + document library.
 */
export default async function WikiIndexPage() {
  const token = await requireAccessToken();
  const orgs = await orgApi.listOrgs(token);
  const activeOrg = await resolveActiveOrg(orgs);
  if (!activeOrg) redirect("/orgs");
  const wikis = await wikiApi.listWikis(token, activeOrg.id);
  const documents = await knowledgeApi.listDocuments(token);
  const canCreate = activeOrg.role !== "viewer";
  const { t } = await getServerI18n();

  return (
    <div className="mx-auto w-full max-w-4xl px-4 pb-16 pt-6 sm:px-8 sm:pt-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1.5">
          <p className="text-[11px] font-medium uppercase tracking-wider text-primary">
            {activeOrg.name}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">{t("wiki.wikis")}</h1>
          <p className="text-sm text-muted-foreground">
            {t("wiki.indexCount", {
              count: wikis.length,
              plural: wikis.length === 1 ? "" : "s",
            })}
          </p>
        </div>
        {canCreate && (
          <Button asChild>
            <Link href="/wiki/new">
              <Plus />
              {t("wiki.newWiki")}
            </Link>
          </Button>
        )}
      </header>

      {wikis.length === 0 ? (
        <EmptyState canCreate={canCreate} t={t} />
      ) : (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {wikis.map((w) => (
            <li key={w.id}>
              <Link
                href={`/wiki/${w.id}`}
                className={cn(
                  "flex h-full flex-col rounded-xl border border-border bg-card p-4",
                  "transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
                )}
              >
                <div className="flex items-start gap-3">
                  <div className="flex size-9 items-center justify-center rounded-lg bg-brand-gradient text-white">
                    <Book className="size-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <h3 className="truncate text-base font-semibold">{w.name}</h3>
                      {w.visibility === "private" && (
                        <Lock className="size-3 shrink-0 text-muted-foreground" />
                      )}
                    </div>
                    <p className="truncate text-xs text-muted-foreground">{w.slug}</p>
                  </div>
                </div>
                {w.description && (
                  <p className="mt-3 line-clamp-2 text-sm text-muted-foreground">
                    {w.description}
                  </p>
                )}
                <p className="mt-auto pt-4 text-xs text-muted-foreground">
                  {t("wiki.access", { role: w.role })} ·{" "}
                  {t("wiki.updated", { time: formatRelative(w.updated_at) })}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <section className="mt-10">
        <DocumentTableClient documents={documents} />
      </section>
    </div>
  );
}

function EmptyState({
  canCreate,
  t,
}: {
  canCreate: boolean;
  t: Awaited<ReturnType<typeof getServerI18n>>["t"];
}) {
  return (
    <div className="rounded-xl border border-dashed border-border bg-card/40 p-12 text-center">
      <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <Book className="size-5" />
      </div>
      <p className="text-base font-medium">{t("wiki.noWikis")}</p>
      <p className="mt-1 text-sm text-muted-foreground">
        {canCreate ? t("wiki.emptyOwner") : t("wiki.emptyViewer")}
      </p>
      {canCreate && (
        <Button asChild className="mt-5">
          <Link href="/wiki/new">
            <Plus />
            {t("wiki.createFirst")}
          </Link>
        </Button>
      )}
    </div>
  );
}
