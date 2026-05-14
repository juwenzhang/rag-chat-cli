"use client";

import {
  AlertCircle,
  Check,
  CloudDownload,
  Download,
  ExternalLink,
  Info,
  Loader2,
} from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api/browser";
import { cn } from "@/lib/utils";

interface Props {
  providerId: string;
  providerName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called once a pull completes successfully so callers can refetch the model list. */
  onPulled?: () => void;
}

interface ProgressFrame {
  status?: string;
  total?: number;
  completed?: number;
  digest?: string;
}

type Stage =
  | { kind: "idle" }
  | { kind: "confirm-local"; tag: string }
  | { kind: "pulling"; tag: string; isCloud: boolean; frame: ProgressFrame }
  | { kind: "done"; tag: string }
  | { kind: "error"; message: string; tag?: string };

/** Cloud-flagged tags pull near-instantly because no GB-sized layers download. */
function isCloudTag(tag: string): boolean {
  return tag.trim().toLowerCase().endsWith("-cloud");
}

export function PullModelDialog({
  providerId,
  providerName,
  open,
  onOpenChange,
  onPulled,
}: Props) {
  const [tag, setTag] = useState("");
  const [description, setDescription] = useState("");
  const [stage, setStage] = useState<Stage>({ kind: "idle" });
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStage({ kind: "idle" });
    setTag("");
    setDescription("");
  }, []);

  const saveDescription = useCallback(
    async (modelTag: string, desc: string) => {
      if (!desc.trim()) return;
      try {
        await api.providers.upsertModelMeta(providerId, modelTag, desc.trim());
      } catch {
        // Description save is non-fatal — pull already succeeded.
      }
    },
    [providerId]
  );

  const startPull = useCallback(
    async (modelTag: string) => {
      const cloud = isCloudTag(modelTag);
      setStage({ kind: "pulling", tag: modelTag, isCloud: cloud, frame: {} });
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const r = await api.providers.pullModel(
          providerId,
          modelTag,
          controller.signal
        );
        if (!r.body) throw new Error("No response stream");
        const reader = r.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let idx: number;
          while ((idx = buffer.indexOf("\n\n")) !== -1) {
            const frame = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);
            const evt = parseSseFrame(frame);
            if (!evt) continue;
            if (evt.event === "progress") {
              setStage({
                kind: "pulling",
                tag: modelTag,
                isCloud: cloud,
                frame: evt.data as ProgressFrame,
              });
            } else if (evt.event === "done") {
              setStage({ kind: "done", tag: modelTag });
              await saveDescription(modelTag, description);
              toast.success(`Pulled ${modelTag}`);
              onPulled?.();
              setTimeout(() => {
                onOpenChange(false);
                reset();
              }, 1200);
              return;
            } else if (evt.event === "error") {
              throw new Error(
                (evt.data as { message?: string }).message ?? "Pull failed"
              );
            }
          }
        }
        // Stream ended without explicit done → treat as success.
        setStage({ kind: "done", tag: modelTag });
        await saveDescription(modelTag, description);
        toast.success(`Pulled ${modelTag}`);
        onPulled?.();
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          setStage({ kind: "idle" });
          return;
        }
        setStage({
          kind: "error",
          message: (err as Error).message,
          tag: modelTag,
        });
      } finally {
        abortRef.current = null;
      }
    },
    [providerId, onOpenChange, onPulled, reset, description, saveDescription]
  );

  const onSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const t = tag.trim();
    if (!t) return;
    if (isCloudTag(t)) {
      void startPull(t);
    } else {
      setStage({ kind: "confirm-local", tag: t });
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (stage.kind === "pulling" && !next) return;
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Pull an Ollama model</DialogTitle>
          <DialogDescription>
            Downloads to{" "}
            <span className="font-mono text-foreground">{providerName}</span>.
            Tags ending in <span className="font-mono">-cloud</span> are
            registered against Ollama Cloud and complete near-instantly.
          </DialogDescription>
        </DialogHeader>

        {stage.kind === "idle" && (
          <form onSubmit={onSubmit} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="pull_tag">Model tag</Label>
              <Input
                id="pull_tag"
                value={tag}
                onChange={(e) => setTag(e.target.value)}
                placeholder="qwen2.5:7b   or   gpt-oss:120b-cloud"
                autoComplete="off"
                autoFocus
              />
              {tag && (
                <p className="text-xs text-muted-foreground">
                  {isCloudTag(tag) ? (
                    <>
                      <CloudDownload className="inline size-3 text-primary" />{" "}
                      Cloud-hosted — pulls instantly.
                    </>
                  ) : (
                    <>This will download from the Ollama library. May be several GB.</>
                  )}
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pull_description">
                Description{" "}
                <span className="text-xs font-normal text-muted-foreground">
                  (optional — shown on hover in the model picker)
                </span>
              </Label>
              <Textarea
                id="pull_description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="e.g. Fast 1.5B chat model for casual replies"
                rows={2}
                maxLength={2000}
                className="resize-none"
              />
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                <a
                  href="https://ollama.com/search"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 hover:text-foreground hover:underline"
                >
                  Browse library
                  <ExternalLink className="size-3" />
                </a>
                <a
                  href="https://ollama.com/search?c=cloud"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 hover:text-foreground hover:underline"
                >
                  Browse cloud models
                  <ExternalLink className="size-3" />
                </a>
                <a
                  href="https://ollama.com/settings/keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 hover:text-foreground hover:underline"
                >
                  Get an API key
                  <ExternalLink className="size-3" />
                </a>
              </div>
            </div>
            <Alert>
              <Info />
              <AlertDescription className="text-[11px] leading-relaxed">
                Cloud models are billed by{" "}
                <span className="font-medium">Ollama</span> per their plan. This
                app is just a runner — like Claude Code Desktop — and doesn&apos;t
                meter usage. Manage your quota at{" "}
                <a
                  href="https://ollama.com/settings"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-foreground"
                >
                  ollama.com/settings
                </a>
                .
              </AlertDescription>
            </Alert>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={!tag.trim()}>
                <Download />
                Pull
              </Button>
            </DialogFooter>
          </form>
        )}

        {stage.kind === "confirm-local" && (
          <div className="space-y-3">
            <Alert variant="warning">
              <AlertCircle />
              <AlertDescription className="text-xs">
                <code className="font-mono text-foreground">{stage.tag}</code>{" "}
                is a local model — Ollama will download all model layers, which
                can be several GB and take many minutes. Continue?
              </AlertDescription>
            </Alert>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setStage({ kind: "idle" })}
              >
                Back
              </Button>
              <Button onClick={() => void startPull(stage.tag)}>
                <Download />
                Yes, pull
              </Button>
            </DialogFooter>
          </div>
        )}

        {stage.kind === "pulling" && (
          <PullingView frame={stage.frame} tag={stage.tag} />
        )}

        {stage.kind === "done" && (
          <div className="flex items-center gap-3 rounded-lg border border-success/40 bg-success/10 p-3 text-sm">
            <Check className="size-4 text-success" />
            <span>
              Successfully pulled{" "}
              <span className="font-mono">{stage.tag}</span>.
            </span>
          </div>
        )}

        {stage.kind === "error" && (
          <div className="space-y-3">
            <Alert variant="destructive">
              <AlertCircle />
              <AlertDescription className="text-xs">
                {stage.message}
              </AlertDescription>
            </Alert>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => onOpenChange(false)}
              >
                Close
              </Button>
              <Button
                onClick={() => {
                  setTag(stage.tag ?? "");
                  setStage({ kind: "idle" });
                }}
              >
                Try again
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function PullingView({ frame, tag }: { frame: ProgressFrame; tag: string }) {
  const total = frame.total;
  const completed = frame.completed;
  const pct =
    total && completed != null
      ? Math.min(100, Math.max(0, Math.round((completed / total) * 100)))
      : null;

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <div className="flex items-center gap-2 text-sm">
          <Loader2 className="size-4 animate-spin text-primary" />
          <span className="font-mono">{tag}</span>
        </div>
        <p className="text-xs text-muted-foreground">
          {frame.status ?? "Starting…"}
          {frame.digest && (
            <span className="ml-2 font-mono text-[10px] opacity-60">
              {frame.digest.slice(0, 16)}…
            </span>
          )}
        </p>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full bg-primary transition-all",
            pct == null && "w-1/3 animate-pulse"
          )}
          style={pct != null ? { width: `${pct}%` } : undefined}
        />
      </div>
      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <span>
          {completed != null && total != null
            ? `${formatBytes(completed)} / ${formatBytes(total)}`
            : "…"}
        </span>
        {pct != null && <span>{pct}%</span>}
      </div>
    </div>
  );
}

interface SseFrame {
  event: string;
  data: Record<string, unknown>;
}

function parseSseFrame(raw: string): SseFrame | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith(":")) continue;
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}

function formatBytes(n: number): string {
  if (n <= 0) return "0";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`;
}
