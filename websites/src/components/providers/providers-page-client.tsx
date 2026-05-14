"use client";

import { ArrowLeft, Plus } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api/browser";
import type { ProviderOut, UserPreferenceOut } from "@/lib/api/types";

import { AddProviderForm } from "./add-provider-form";
import { PreferencesCard } from "./preferences-card";
import { ProviderCard } from "./provider-card";

interface Props {
  initialProviders: ProviderOut[];
  initialPreferences: UserPreferenceOut;
}

/** Providers settings page — add/edit LLM providers + per-user defaults. */
export function ProvidersPageClient({
  initialProviders,
  initialPreferences,
}: Props) {
  const [providers, setProviders] = useState(initialProviders);
  const [pref, setPref] = useState(initialPreferences);
  const [adding, setAdding] = useState(initialProviders.length === 0);

  const refetch = useCallback(async () => {
    try {
      const [p, q] = await Promise.all([
        api.providers.list(),
        api.me.getPreferences(),
      ]);
      setProviders(p);
      setPref(q);
    } catch (err) {
      toast.error(`Refresh failed: ${(err as Error).message}`);
    }
  }, []);

  return (
    <div className="h-full overflow-y-auto bg-muted/30">
      <div className="mx-auto max-w-3xl space-y-6 px-6 py-10">
        <div className="flex items-center gap-3">
          <Button asChild variant="ghost" size="icon" aria-label="Back to chat">
            <Link href="/chat">
              <ArrowLeft />
            </Link>
          </Button>
          <div className="flex-1">
            <h1 className="text-2xl font-semibold tracking-tight">
              LLM providers
            </h1>
            <p className="text-sm text-muted-foreground">
              Self-host: bring your own Ollama, OpenAI key, or any
              OpenAI-compatible endpoint. Keys are encrypted at rest.
            </p>
          </div>
          {!adding && (
            <Button onClick={() => setAdding(true)} size="sm">
              <Plus /> Add provider
            </Button>
          )}
        </div>

        {adding && (
          <AddProviderForm
            onClose={() => setAdding(false)}
            onCreated={() => {
              setAdding(false);
              void refetch();
            }}
          />
        )}

        <PreferencesCard
          providers={providers}
          pref={pref}
          onUpdated={(p) => setPref(p)}
        />

        <div className="space-y-3">
          {providers.length === 0 && !adding ? (
            <Card>
              <CardContent className="py-10 text-center">
                <p className="text-sm text-muted-foreground">
                  No providers yet. Add one to start chatting.
                </p>
              </CardContent>
            </Card>
          ) : (
            providers.map((p) => (
              <ProviderCard
                key={p.id}
                provider={p}
                isUserDefault={pref.default_provider_id === p.id}
                onChanged={refetch}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
