import { Book, Lock, Plus } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Button } from "@/components/ui/button";
import { resolveActiveOrg } from "@/lib/active-org";
import { orgApi, wikiApi } from "@/lib/api";
import { getAccessToken, getCurrentUser } from "@/lib/session";
import { cn, formatRelative } from "@/lib/utils";

export const dynamic = "force-dynamic";

/**
 * /wiki — workspace's wiki list.
 *
 * No auto-jump anywhere. The user always sees the list and clicks the
 * wiki they want. Empty state explicitly invites them to create one.
 */
export default async function WikiIndexPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  const token = await getAccessToken();
  if (!token) redirect("/login");

  const orgs = await orgApi.listOrgs(token);
  const activeOrg = await resolveActiveOrg(orgs);
  if (!activeOrg) redirect("/orgs");
  const wikis = await wikiApi.listWikis(token, activeOrg.id);
  const canCreate = activeOrg.role !== "viewer";

  return (
    <div className="mx-auto w-full max-w-4xl px-4 pb-16 pt-6 sm:px-8 sm:pt-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1.5">
          <p className="text-[11px] font-medium uppercase tracking-wider text-primary">
            {activeOrg.name}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">Wikis</h1>
          <p className="text-sm text-muted-foreground">
            {wikis.length} wiki{wikis.length === 1 ? "" : "s"} in this
            workspace
          </p>
        </div>
        {canCreate && (
          <Button asChild>
            <Link href="/wiki/new">
              <Plus />
              New wiki
            </Link>
          </Button>
        )}
      </header>

      {wikis.length === 0 ? (
        <EmptyState canCreate={canCreate} />
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
                      <h3 className="truncate text-base font-semibold">
                        {w.name}
                      </h3>
                      {w.visibility === "private" && (
                        <Lock className="size-3 shrink-0 text-muted-foreground" />
                      )}
                    </div>
                    <p className="truncate text-xs text-muted-foreground">
                      {w.slug}
                    </p>
                  </div>
                </div>
                {w.description && (
                  <p className="mt-3 line-clamp-2 text-sm text-muted-foreground">
                    {w.description}
                  </p>
                )}
                <p className="mt-auto pt-4 text-xs text-muted-foreground">
                  <span className="capitalize">{w.role}</span> access ·{" "}
                  updated {formatRelative(w.updated_at)}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EmptyState({ canCreate }: { canCreate: boolean }) {
  return (
    <div className="rounded-xl border border-dashed border-border bg-card/40 p-12 text-center">
      <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <Book className="size-5" />
      </div>
      <p className="text-base font-medium">No wikis yet</p>
      <p className="mt-1 text-sm text-muted-foreground">
        {canCreate
          ? "A wiki is a named knowledge base — group related pages together, share with teammates, and let the AI search inside (later)."
          : "Pages live inside wikis. An owner of this workspace needs to create one before you can write."}
      </p>
      {canCreate && (
        <Button asChild className="mt-5">
          <Link href="/wiki/new">
            <Plus />
            Create your first wiki
          </Link>
        </Button>
      )}
    </div>
  );
}
