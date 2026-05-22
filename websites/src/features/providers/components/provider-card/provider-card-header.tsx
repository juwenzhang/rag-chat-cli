"use client";

import { Check, Key, Star, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardHeader } from "@/components/ui/card";
import type { ProviderOut } from "@/lib/api/shared/types";
import { cn } from "@/lib/utils";

export function ProviderCardHeader({
  provider,
  isUserDefault,
  busy,
  onOpenApiKey,
  onToggleDefault,
  onToggleEnabled,
  onRequestDelete,
}: {
  provider: ProviderOut;
  isUserDefault: boolean;
  busy: boolean;
  onOpenApiKey: () => void;
  onToggleDefault: () => void;
  onToggleEnabled: () => void;
  onRequestDelete: () => void;
}) {
  return (
    <CardHeader className="flex-row items-start justify-between space-y-0 gap-3">
      <div className="min-w-0 flex-1 space-y-1">
        <ProviderTitle provider={provider} isUserDefault={isUserDefault} />
        <ProviderEndpoint provider={provider} onOpenApiKey={onOpenApiKey} />
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Button
          variant={provider.has_api_key ? "ghost" : "outline"}
          size="sm"
          onClick={onOpenApiKey}
          disabled={busy}
        >
          <Key className={cn("size-3.5", provider.has_api_key && "text-success")} />
          <span className="hidden sm:inline">
            {provider.has_api_key ? "API Key" : "Set API Key"}
          </span>
        </Button>
        <Button variant="ghost" size="sm" onClick={onToggleDefault} disabled={busy}>
          <Star className={cn(provider.is_default && "fill-current text-yellow-500")} />
          <span className="hidden sm:inline">
            {provider.is_default ? "Unset default" : "Make default"}
          </span>
        </Button>
        <Button variant="ghost" size="sm" onClick={onToggleEnabled} disabled={busy}>
          {provider.enabled ? "Disable" : "Enable"}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={onRequestDelete}
          disabled={busy}
          aria-label="Delete provider"
        >
          <Trash2 />
        </Button>
      </div>
    </CardHeader>
  );
}

function ProviderTitle({
  provider,
  isUserDefault,
}: {
  provider: ProviderOut;
  isUserDefault: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <h3 className="truncate text-base font-medium">{provider.name}</h3>
      <Badge variant="outline" className="text-[10px] uppercase">
        {provider.type}
      </Badge>
      {provider.is_default && (
        <Badge variant="success" className="gap-1 text-[10px]">
          <Star className="size-3" />
          default
        </Badge>
      )}
      {!provider.enabled && (
        <Badge variant="secondary" className="text-[10px]">
          disabled
        </Badge>
      )}
      {isUserDefault && !provider.is_default && (
        <Badge variant="secondary" className="text-[10px]">
          user default
        </Badge>
      )}
    </div>
  );
}

function ProviderEndpoint({
  provider,
  onOpenApiKey,
}: {
  provider: ProviderOut;
  onOpenApiKey: () => void;
}) {
  return (
    <p className="truncate text-xs text-muted-foreground">
      {provider.base_url}
      <button
        type="button"
        onClick={onOpenApiKey}
        className={cn(
          "ml-2 inline-flex items-center gap-1 text-[10px] transition-colors hover:text-foreground",
          provider.has_api_key ? "text-success" : "text-muted-foreground/60"
        )}
      >
        {provider.has_api_key ? (
          <>
            <Check className="size-3" />
            API key stored
          </>
        ) : (
          <>
            <Key className="size-3" />
            Set API key
          </>
        )}
      </button>
    </p>
  );
}
