"use client";

import { Brain, ImagePlus, Loader2, Send, Square, X } from "lucide-react";
import type { ClipboardEvent, ComponentProps, KeyboardEvent, RefObject } from "react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { buildOutgoingContent } from "@/features/chat/utils/outgoing-content";
import { api } from "@/lib/api/browser";
import type {
  AssetOut,
  ProviderOut,
  SessionMeta,
  ThinkMode,
  UserPreferenceOut,
} from "@/lib/api/shared/types";
import { cn } from "@/lib/utils";

import { ModelSelector } from "../model-selector";

type FormSubmitEvent = Parameters<NonNullable<ComponentProps<"form">["onSubmit"]>>[0];

/**
 * An entry in the composer's attachment row. ``ready`` items are real
 * uploaded assets; ``pending`` items are local placeholders with an
 * object-URL preview while the upload is in flight. They share the
 * same ``key`` (the ``uploadId``/``asset.id``) so the UI never flashes
 * an empty slot when the placeholder is swapped for the real asset.
 */
type Attachment =
  | {
      kind: "pending";
      uploadId: string;
      filename: string;
      previewUrl: string;
      progress: number;
    }
  | {
      kind: "ready";
      uploadId: string;
      asset: AssetOut;
    };

function newUploadId(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof (crypto as Crypto).randomUUID === "function"
  ) {
    return (crypto as Crypto).randomUUID();
  }
  return `upl_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

export interface ChatComposerCopy {
  placeholder: string;
  disclaimer: string;
  stop: string;
  send: string;
  ragOn: string;
  ragOff: string;
  ragEnabledTip: string;
  ragDisabledTip: string;
  thinkOn: string;
  thinkOff: string;
  thinkEnabledTip: string;
  thinkDisabledTip: string;
}

export function ChatComposer({
  sessionId,
  sessionMeta,
  input,
  streaming,
  useRag,
  think,
  providerId,
  model,
  inputRef,
  initialProviders,
  initialPreferences,
  copy,
  onInputChange,
  onSubmit,
  onToggleRag,
  onToggleThink,
  onModelChange,
  onAbort,
}: {
  sessionId: string;
  sessionMeta?: SessionMeta | null;
  input: string;
  streaming: boolean;
  useRag: boolean;
  think: ThinkMode;
  providerId: string | null;
  model: string | null;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  initialProviders: ProviderOut[];
  initialPreferences: UserPreferenceOut;
  copy: ChatComposerCopy;
  onInputChange: (next: string) => void;
  onSubmit: (content: string) => boolean;
  onToggleRag: () => void;
  onToggleThink: () => void;
  onModelChange: (next: { provider_id: string | null; model: string | null }) => void;
  onAbort: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const objectUrlsRef = useRef<Set<string>>(new Set());

  const pendingCount = attachments.reduce(
    (n, a) => (a.kind === "pending" ? n + 1 : n),
    0
  );
  const uploading = pendingCount > 0;
  const readyAssets = attachments
    .filter((a): a is Extract<Attachment, { kind: "ready" }> => a.kind === "ready")
    .map((a) => a.asset);
  const hasAssets = readyAssets.length > 0;

  // Free any object URLs we created if the component goes away while
  // an upload is still pending.
  useEffect(() => {
    const urls = objectUrlsRef.current;
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
      urls.clear();
    };
  }, []);

  const uploadOne = async (file: File) => {
    const uploadId = newUploadId();
    const previewUrl = URL.createObjectURL(file);
    objectUrlsRef.current.add(previewUrl);
    setAttachments((prev) => [
      ...prev,
      {
        kind: "pending",
        uploadId,
        filename: file.name,
        previewUrl,
        progress: 0,
      },
    ]);

    try {
      const asset = await api.assets.uploadImage(file, {
        onProgress: ({ ratio }) => {
          setAttachments((prev) =>
            prev.map((a) =>
              a.kind === "pending" && a.uploadId === uploadId
                ? { ...a, progress: ratio }
                : a
            )
          );
        },
      });
      setAttachments((prev) => {
        // If the user removed the placeholder while the upload was in
        // flight, drop the asset on the floor — it's content-hashed
        // server-side so re-uploading later costs nothing.
        const exists = prev.some((a) => a.kind === "pending" && a.uploadId === uploadId);
        if (!exists) return prev;
        return prev.map((a) =>
          a.kind === "pending" && a.uploadId === uploadId
            ? { kind: "ready", uploadId, asset }
            : a
        );
      });
    } catch (err) {
      setAttachments((prev) =>
        prev.filter((a) => !(a.kind === "pending" && a.uploadId === uploadId))
      );
      toast.error((err as Error).message || `Failed to upload ${file.name}`);
    } finally {
      URL.revokeObjectURL(previewUrl);
      objectUrlsRef.current.delete(previewUrl);
    }
  };

  const uploadImages = async (files: File[]) => {
    const imageFiles = files.filter((file) => file.type.startsWith("image/"));
    if (imageFiles.length === 0) return;
    // Parallel uploads — each appends its own placeholder synchronously
    // before awaiting, so the user sees every dropped image right away.
    await Promise.all(imageFiles.map(uploadOne));
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeAttachment = (uploadId: string) => {
    setAttachments((prev) => prev.filter((a) => a.uploadId !== uploadId));
  };

  const submitCurrent = () => {
    if (streaming || uploading) return;
    const content = buildOutgoingContent(input, readyAssets);
    if (!content) return;
    if (onSubmit(content)) {
      // Only clear ready ones; if anything is somehow still pending we
      // leave it so the user doesn't lose in-flight uploads. (Send is
      // gated by ``uploading`` anyway, so this is a defence-in-depth.)
      setAttachments((prev) => prev.filter((a) => a.kind === "pending"));
    }
  };

  const handleSubmit = (event: FormSubmitEvent) => {
    event.preventDefault();
    submitCurrent();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.ctrlKey && !event.metaKey) {
      event.preventDefault();
      submitCurrent();
    }
  };

  const handlePaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(event.clipboardData.items)
      .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
      .map((item) => item.getAsFile())
      .filter((file): file is File => Boolean(file));
    if (files.length === 0) return;
    event.preventDefault();
    void uploadImages(files);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="border-t border-border bg-background/80 px-3 py-3 backdrop-blur sm:px-4 sm:py-4"
    >
      <div className="mx-auto max-w-3xl">
        <div
          className={cn(
            "relative flex flex-col gap-1 rounded-2xl border border-border bg-card p-2 shadow-sm transition-all",
            "focus-within:border-primary/50 focus-within:shadow-md focus-within:shadow-primary/5"
          )}
        >
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 px-2 pt-1">
              {attachments.map((attachment) => (
                <AttachmentChip
                  key={attachment.uploadId}
                  attachment={attachment}
                  onRemove={() => removeAttachment(attachment.uploadId)}
                />
              ))}
            </div>
          )}
          <Textarea
            ref={inputRef}
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={copy.placeholder}
            rows={1}
            className={cn(
              "min-h-11 resize-none border-0 bg-transparent px-2 py-2.5 shadow-none focus-visible:ring-0",
              "max-h-50"
            )}
            style={{ height: "auto" }}
            onInput={(event) => {
              const el = event.currentTarget;
              el.style.height = "auto";
              el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
            }}
            disabled={streaming}
          />
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            className="hidden"
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              if (files.length > 0) void uploadImages(files);
            }}
          />
          <ComposerActions
            sessionId={sessionId}
            sessionMeta={sessionMeta}
            input={input}
            streaming={streaming}
            useRag={useRag}
            think={think}
            providerId={providerId}
            model={model}
            initialProviders={initialProviders}
            initialPreferences={initialPreferences}
            copy={copy}
            uploading={uploading}
            hasAssets={hasAssets}
            onPickImage={() => fileInputRef.current?.click()}
            onToggleRag={onToggleRag}
            onToggleThink={onToggleThink}
            onModelChange={onModelChange}
            onAbort={onAbort}
          />
        </div>
        <p className="mt-2 hidden text-center text-[11px] text-muted-foreground sm:block">
          {copy.disclaimer}
        </p>
      </div>
    </form>
  );
}

/**
 * Single chip in the attachment row. Shows a thumbnail (preview URL
 * for pending uploads, real CDN URL for ready ones), filename, and a
 * remove button. Pending chips overlay a spinner + progress bar so
 * the user sees that something is in flight.
 */
function AttachmentChip({
  attachment,
  onRemove,
}: {
  attachment: Attachment;
  onRemove: () => void;
}) {
  const isPending = attachment.kind === "pending";
  const src =
    attachment.kind === "pending" ? attachment.previewUrl : attachment.asset.url;
  const filename =
    attachment.kind === "pending" ? attachment.filename : attachment.asset.filename;
  // Clamp progress to a visible minimum so the bar is never invisible
  // before the first ack arrives.
  const progressPct = isPending
    ? Math.max(4, Math.round(attachment.progress * 100))
    : 100;

  return (
    <div
      className={cn(
        "relative flex max-w-full items-center gap-2 rounded-lg border border-border bg-muted/50 px-2 py-1 text-xs",
        isPending && "opacity-90"
      )}
    >
      <div className="relative size-8 shrink-0">
        {/* eslint-disable-next-line @next/next/no-img-element -- thumbnails come from the same origin */}
        <img
          src={src}
          alt={filename}
          className={cn("size-8 rounded object-cover", isPending && "brightness-75")}
        />
        {isPending && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <Loader2 className="size-4 animate-spin text-white drop-shadow" />
          </div>
        )}
      </div>
      <span className="max-w-40 truncate">{filename}</span>
      <button
        type="button"
        onClick={onRemove}
        className="rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
        aria-label="Remove image"
      >
        <X className="size-3" />
      </button>
      {isPending && (
        <span
          className="pointer-events-none absolute inset-x-0 bottom-0 h-0.5 origin-left rounded-b-lg bg-primary transition-[width] duration-150"
          style={{ width: `${progressPct}%` }}
          aria-hidden
        />
      )}
    </div>
  );
}

function ComposerActions({
  sessionId,
  sessionMeta,
  input,
  streaming,
  useRag,
  think,
  providerId,
  model,
  initialProviders,
  initialPreferences,
  copy,
  uploading,
  hasAssets,
  onPickImage,
  onToggleRag,
  onToggleThink,
  onModelChange,
  onAbort,
}: {
  sessionId: string;
  sessionMeta?: SessionMeta | null;
  input: string;
  streaming: boolean;
  useRag: boolean;
  think: ThinkMode;
  providerId: string | null;
  model: string | null;
  initialProviders: ProviderOut[];
  initialPreferences: UserPreferenceOut;
  copy: ChatComposerCopy;
  uploading: boolean;
  hasAssets: boolean;
  onPickImage: () => void;
  onToggleRag: () => void;
  onToggleThink: () => void;
  onModelChange: (next: { provider_id: string | null; model: string | null }) => void;
  onAbort: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1 border-t border-border/60 pt-1.5">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        disabled={streaming}
        onClick={onPickImage}
        className="gap-1.5 px-2 text-xs font-normal text-muted-foreground hover:text-foreground sm:px-3"
      >
        {uploading ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : (
          <ImagePlus className="size-3.5" />
        )}
        <span>Image</span>
      </Button>
      <RagToggle
        enabled={useRag}
        disabled={streaming}
        copy={copy}
        onToggle={onToggleRag}
      />
      <ThinkToggle
        enabled={think !== false}
        disabled={streaming}
        copy={copy}
        onToggle={onToggleThink}
      />
      <div className="ml-auto flex min-w-0 items-center gap-1">
        <ModelSelector
          sessionId={sessionId}
          initialProviderId={providerId ?? sessionMeta?.provider_id ?? null}
          initialModel={model ?? sessionMeta?.model ?? null}
          initialProviders={initialProviders}
          initialPreferences={initialPreferences}
          disabled={streaming}
          onChange={onModelChange}
        />
        {streaming ? (
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={onAbort}
            className="size-9 shrink-0 rounded-xl"
            aria-label={copy.stop}
          >
            <Square className="size-4 fill-current" />
          </Button>
        ) : (
          <Button
            type="submit"
            size="icon"
            disabled={(!input.trim() && !hasAssets) || uploading}
            className="size-9 shrink-0 rounded-xl"
            aria-label={copy.send}
          >
            <Send className="size-4" />
          </Button>
        )}
      </div>
    </div>
  );
}

function ThinkToggle({
  enabled,
  disabled,
  copy,
  onToggle,
}: {
  enabled: boolean;
  disabled: boolean;
  copy: ChatComposerCopy;
  onToggle: () => void;
}) {
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onToggle}
            disabled={disabled}
            className={cn(
              "gap-1.5 px-2 text-xs font-normal sm:px-3",
              enabled ? "text-foreground" : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Brain
              className={cn(
                "size-3.5",
                enabled ? "text-primary" : "text-muted-foreground"
              )}
            />
            <span>Think</span>
            <Badge
              variant={enabled ? "success" : "outline"}
              className="ml-0.5 text-[9px]"
            >
              {enabled ? copy.thinkOn : copy.thinkOff}
            </Badge>
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          {enabled ? copy.thinkEnabledTip : copy.thinkDisabledTip}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

function RagToggle({
  enabled,
  disabled,
  copy,
  onToggle,
}: {
  enabled: boolean;
  disabled: boolean;
  copy: ChatComposerCopy;
  onToggle: () => void;
}) {
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onToggle}
            disabled={disabled}
            className={cn(
              "gap-1.5 px-2 text-xs font-normal sm:px-3",
              enabled ? "text-foreground" : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Brain
              className={cn(
                "size-3.5",
                enabled ? "text-primary" : "text-muted-foreground"
              )}
            />
            <span>RAG</span>
            <Badge
              variant={enabled ? "success" : "outline"}
              className="ml-0.5 text-[9px]"
            >
              {enabled ? copy.ragOn : copy.ragOff}
            </Badge>
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          {enabled ? copy.ragEnabledTip : copy.ragDisabledTip}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
