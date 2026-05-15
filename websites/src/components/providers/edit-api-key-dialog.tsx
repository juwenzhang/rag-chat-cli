"use client";

import { Eye, EyeOff, Key, Loader2, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/browser";
import type { ProviderOut } from "@/lib/api/types";

interface Props {
  provider: ProviderOut | null;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}

/**
 * Dialog to set, update, or clear the API key for a provider.
 * The key is sent to the backend where it's Fernet-encrypted at rest.
 * The server never returns the plaintext — only `has_api_key: bool`.
 */
export function EditApiKeyDialog({ provider, onOpenChange, onSaved }: Props) {
  const [key, setKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    if (provider) {
      setKey("");
      setShowKey(false);
    }
  }, [provider]);

  const onSave = async () => {
    if (!provider || !key.trim()) return;
    setSaving(true);
    try {
      await api.providers.update(provider.id, { api_key: key.trim() });
      toast.success("API key saved");
      onSaved();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const onClear = async () => {
    if (!provider) return;
    setClearing(true);
    try {
      await api.providers.update(provider.id, { clear_api_key: true });
      toast.success("API key cleared");
      onSaved();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setClearing(false);
    }
  };

  return (
    <Dialog open={provider !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Key className="size-4 text-primary" />
            API Key — {provider?.name}
          </DialogTitle>
          <DialogDescription>
            {provider?.type === "openai"
              ? "Enter your OpenAI-compatible API key. It will be encrypted at rest and used for all requests to this provider."
              : "Ollama usually runs locally without a key. Set one here only if your instance requires authentication."}
          </DialogDescription>
        </DialogHeader>
        {provider && (
          <>
            <div className="space-y-3">
              {provider.has_api_key && (
                <div className="rounded-md bg-success/10 px-3 py-2 text-xs text-success">
                  A key is currently stored. Enter a new one below to replace
                  it, or clear it entirely.
                </div>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="api-key-input">
                  {provider.has_api_key ? "New API key" : "API key"}
                </Label>
                <div className="relative">
                  <Input
                    id="api-key-input"
                    type={showKey ? "text" : "password"}
                    value={key}
                    onChange={(e) => setKey(e.target.value)}
                    placeholder={
                      provider.type === "openai"
                        ? "sk-..."
                        : "Bearer token or API key"
                    }
                    autoFocus
                    className="pr-10 font-mono text-xs"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((v) => !v)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    aria-label={showKey ? "Hide key" : "Show key"}
                  >
                    {showKey ? (
                      <EyeOff className="size-3.5" />
                    ) : (
                      <Eye className="size-3.5" />
                    )}
                  </button>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Stored encrypted. Never exposed in API responses.
                </p>
              </div>
            </div>
            <DialogFooter className="gap-2 sm:gap-0">
              {provider.has_api_key && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={onClear}
                  disabled={clearing || saving}
                  className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                >
                  {clearing ? (
                    <Loader2 className="animate-spin" />
                  ) : (
                    <Trash2 />
                  )}
                  Clear key
                </Button>
              )}
              <div className="flex-1" />
              <Button
                type="button"
                variant="ghost"
                onClick={() => onOpenChange(false)}
                disabled={saving || clearing}
              >
                Cancel
              </Button>
              <Button
                onClick={onSave}
                disabled={!key.trim() || saving || clearing}
              >
                {saving ? <Loader2 className="animate-spin" /> : <Save />}
                {provider.has_api_key ? "Update key" : "Save key"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
