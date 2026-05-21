"use client";

import { ExternalLink, Loader2, Plus, RefreshCcw } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export type ProviderKind = "ollama" | "openai";

export interface ConnectivityResult {
  ok: boolean;
  detail: string;
}

export function ProviderTypePicker({
  value,
  onChange,
}: {
  value: ProviderKind;
  onChange: (next: ProviderKind) => void;
}) {
  return (
    <div className="flex gap-2">
      {(["ollama", "openai"] as const).map((type) => (
        <button
          key={type}
          type="button"
          onClick={() => onChange(type)}
          className={cn(
            "flex-1 rounded-lg border px-3 py-2 text-sm transition-colors",
            value === type
              ? "border-primary bg-primary/5 text-foreground"
              : "border-border text-muted-foreground hover:bg-muted/40"
          )}
        >
          <div className="font-medium">
            {type === "ollama" ? "Ollama" : "OpenAI-compatible"}
          </div>
          <div className="text-[11px] text-muted-foreground">
            {type === "ollama"
              ? "Local or hosted Ollama"
              : "OpenAI / OpenRouter / DeepSeek / Together / …"}
          </div>
        </button>
      ))}
    </div>
  );
}

export function ProviderConnectionFields({
  type,
  name,
  baseUrl,
  apiKey,
  onNameChange,
  onBaseUrlChange,
  onApiKeyChange,
}: {
  type: ProviderKind;
  name: string;
  baseUrl: string;
  apiKey: string;
  onNameChange: (next: string) => void;
  onBaseUrlChange: (next: string) => void;
  onApiKeyChange: (next: string) => void;
}) {
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="name">Name</Label>
          <Input
            id="name"
            placeholder="local-ollama"
            value={name}
            onChange={(event) => onNameChange(event.target.value)}
            required
            maxLength={64}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="base_url">Base URL</Label>
          <Input
            id="base_url"
            value={baseUrl}
            onChange={(event) => onBaseUrlChange(event.target.value)}
            required
            type="url"
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <Label htmlFor="api_key">
            API key{" "}
            <span className="text-xs text-muted-foreground">
              ({type === "ollama"
                ? "optional for local · required for cloud"
                : "usually required"})
            </span>
          </Label>
          {type === "ollama" && <OllamaKeyLink />}
        </div>
        <Input
          id="api_key"
          type="password"
          autoComplete="off"
          placeholder={
            type === "ollama"
              ? "Leave empty for local Ollama · paste key for cloud"
              : "sk-…"
          }
          value={apiKey}
          onChange={(event) => onApiKeyChange(event.target.value)}
        />
      </div>
    </>
  );
}

export function ProviderFormOptions({
  isDefault,
  skipTest,
  onDefaultChange,
  onSkipTestChange,
}: {
  isDefault: boolean;
  skipTest: boolean;
  onDefaultChange: (next: boolean) => void;
  onSkipTestChange: (next: boolean) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-4 text-sm">
      <label className="inline-flex items-center gap-2">
        <input
          type="checkbox"
          checked={isDefault}
          onChange={(event) => onDefaultChange(event.target.checked)}
          className="size-4 rounded border-input"
        />
        Make this my default provider
      </label>
      <label className="inline-flex items-center gap-2 text-muted-foreground">
        <input
          type="checkbox"
          checked={skipTest}
          onChange={(event) => onSkipTestChange(event.target.checked)}
          className="size-4 rounded border-input"
        />
        Skip connectivity test
      </label>
    </div>
  );
}

export function ConnectivityResultAlert({ result }: { result: ConnectivityResult | null }) {
  if (!result) return null;
  return (
    <Alert variant={result.ok ? "default" : "destructive"}>
      <AlertDescription className="text-xs">
        {result.ok ? "OK — " : "Failed — "}
        {result.detail}
      </AlertDescription>
    </Alert>
  );
}

export function AddProviderActions({
  testing,
  submitting,
  canTest,
  canSubmit,
  onTest,
}: {
  testing: boolean;
  submitting: boolean;
  canTest: boolean;
  canSubmit: boolean;
  onTest: () => void;
}) {
  return (
    <div className="flex items-center justify-end gap-2 pt-1">
      <Button
        type="button"
        variant="outline"
        onClick={onTest}
        disabled={testing || !canTest}
      >
        {testing ? <Loader2 className="animate-spin" /> : <RefreshCcw />}
        Test connection
      </Button>
      <Button type="submit" disabled={submitting || !canSubmit}>
        {submitting ? <Loader2 className="animate-spin" /> : <Plus />}
        Add provider
      </Button>
    </div>
  );
}

function OllamaKeyLink() {
  return (
    <a
      href="https://ollama.com/settings/keys"
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground hover:underline"
    >
      Get your Ollama key
      <ExternalLink className="size-3" />
    </a>
  );
}
