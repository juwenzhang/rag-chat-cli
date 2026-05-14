"use client";

import { ExternalLink, Loader2, Plus, RefreshCcw, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/browser";
import { cn } from "@/lib/utils";

/** New-provider form card — type/URL/key + connectivity probe before save. */
export function AddProviderForm({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [type, setType] = useState<"ollama" | "openai">("ollama");
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("http://localhost:11434");
  const [apiKey, setApiKey] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [skipTest, setSkipTest] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    detail: string;
  } | null>(null);

  const onTypeChange = (next: "ollama" | "openai") => {
    setType(next);
    setTestResult(null);
    if (next === "ollama" && (!baseUrl || baseUrl.includes("openai"))) {
      setBaseUrl("http://localhost:11434");
    }
    if (next === "openai" && baseUrl.includes("11434")) {
      setBaseUrl("https://api.openai.com/v1");
    }
  };

  const onTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      setTestResult(
        await api.providers.test({
          type,
          base_url: baseUrl,
          api_key: apiKey || undefined,
        })
      );
    } catch (err) {
      setTestResult({ ok: false, detail: (err as Error).message });
    } finally {
      setTesting(false);
    }
  };

  const onSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.providers.create({
        name: name.trim(),
        type,
        base_url: baseUrl,
        api_key: apiKey || undefined,
        is_default: isDefault,
        test_connectivity: !skipTest,
      });
      toast.success(`Added provider ${name}`);
      onCreated();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="text-base">Add a provider</CardTitle>
          <CardDescription>
            Type, URL, and (if needed) an API key. We probe the endpoint before
            saving unless you opt out.
          </CardDescription>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Cancel">
          <X />
        </Button>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={onSubmit}>
          <div className="flex gap-2">
            {(["ollama", "openai"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => onTypeChange(t)}
                className={cn(
                  "flex-1 rounded-lg border px-3 py-2 text-sm transition-colors",
                  type === t
                    ? "border-primary bg-primary/5 text-foreground"
                    : "border-border text-muted-foreground hover:bg-muted/40"
                )}
              >
                <div className="font-medium">
                  {t === "ollama" ? "Ollama" : "OpenAI-compatible"}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  {t === "ollama"
                    ? "Local or hosted Ollama"
                    : "OpenAI / OpenRouter / DeepSeek / Together / …"}
                </div>
              </button>
            ))}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                placeholder="local-ollama"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={64}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="base_url">Base URL</Label>
              <Input
                id="base_url"
                value={baseUrl}
                onChange={(e) => {
                  setBaseUrl(e.target.value);
                  setTestResult(null);
                }}
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
              {type === "ollama" && (
                <a
                  href="https://ollama.com/settings/keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground hover:underline"
                >
                  Get your Ollama key
                  <ExternalLink className="size-3" />
                </a>
              )}
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
              onChange={(e) => {
                setApiKey(e.target.value);
                setTestResult(null);
              }}
            />
          </div>

          <div className="flex flex-wrap items-center gap-4 text-sm">
            <label className="inline-flex items-center gap-2">
              <input
                type="checkbox"
                checked={isDefault}
                onChange={(e) => setIsDefault(e.target.checked)}
                className="size-4 rounded border-input"
              />
              Make this my default provider
            </label>
            <label className="inline-flex items-center gap-2 text-muted-foreground">
              <input
                type="checkbox"
                checked={skipTest}
                onChange={(e) => setSkipTest(e.target.checked)}
                className="size-4 rounded border-input"
              />
              Skip connectivity test
            </label>
          </div>

          {testResult && (
            <Alert variant={testResult.ok ? "default" : "destructive"}>
              <AlertDescription className="text-xs">
                {testResult.ok ? "OK — " : "Failed — "}
                {testResult.detail}
              </AlertDescription>
            </Alert>
          )}

          <div className="flex items-center justify-end gap-2 pt-1">
            <Button
              type="button"
              variant="outline"
              onClick={onTest}
              disabled={testing || !baseUrl}
            >
              {testing ? (
                <Loader2 className="animate-spin" />
              ) : (
                <RefreshCcw />
              )}
              Test connection
            </Button>
            <Button type="submit" disabled={submitting || !name.trim()}>
              {submitting ? <Loader2 className="animate-spin" /> : <Plus />}
              Add provider
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
