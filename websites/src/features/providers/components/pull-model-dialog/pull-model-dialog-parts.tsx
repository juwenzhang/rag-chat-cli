"use client";

import {
  AlertCircle,
  Check,
  CloudDownload,
  Download,
  ExternalLink,
  Info,
} from "lucide-react";
import type { FormEvent, ReactNode } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
export interface ProgressFrame {
  status?: string;
  total?: number;
  completed?: number;
  digest?: string;
}

export function PullModelIdleForm({
  tag,
  description,
  isCloud,
  onTagChange,
  onDescriptionChange,
  onSubmit,
  onCancel,
}: {
  tag: string;
  description: string;
  isCloud: (tag: string) => boolean;
  onTagChange: (next: string) => void;
  onDescriptionChange: (next: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
}) {
  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="pull_tag">Model tag</Label>
        <Input
          id="pull_tag"
          value={tag}
          onChange={(event) => onTagChange(event.target.value)}
          placeholder="qwen2.5:7b   or   gpt-oss:120b-cloud"
          autoComplete="off"
          autoFocus
        />
        {tag && <ModelTagHint cloud={isCloud(tag)} />}
      </div>
      <PullDescriptionField value={description} onChange={onDescriptionChange} />
      <CloudBillingNotice />
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={!tag.trim()}>
          <Download />
          Pull
        </Button>
      </DialogFooter>
    </form>
  );
}

export function PullModelConfirmStep({
  tag,
  onBack,
  onConfirm,
}: {
  tag: string;
  onBack: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="space-y-3">
      <Alert variant="warning">
        <AlertCircle />
        <AlertDescription className="text-xs">
          <code className="font-mono text-foreground">{tag}</code> is a local model —
          Ollama will download all model layers, which can be several GB and take many
          minutes. Continue?
        </AlertDescription>
      </Alert>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onBack}>
          Back
        </Button>
        <Button onClick={onConfirm}>
          <Download />
          Yes, pull
        </Button>
      </DialogFooter>
    </div>
  );
}

export function PullModelDoneStep({ tag }: { tag: string }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-success/40 bg-success/10 p-3 text-sm">
      <Check className="size-4 text-success" />
      <span>
        Successfully pulled <span className="font-mono">{tag}</span>.
      </span>
    </div>
  );
}

export function PullModelErrorStep({
  message,
  onClose,
  onRetry,
}: {
  message: string;
  onClose: () => void;
  onRetry: () => void;
}) {
  return (
    <div className="space-y-3">
      <Alert variant="destructive">
        <AlertCircle />
        <AlertDescription className="text-xs">{message}</AlertDescription>
      </Alert>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          Close
        </Button>
        <Button onClick={onRetry}>Try again</Button>
      </DialogFooter>
    </div>
  );
}

function PullDescriptionField({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor="pull_description">
        Description{" "}
        <span className="text-xs font-normal text-muted-foreground">
          (optional — shown on hover in the model picker)
        </span>
      </Label>
      <Textarea
        id="pull_description"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="e.g. Fast 1.5B chat model for casual replies"
        rows={2}
        maxLength={2000}
        className="resize-none"
      />
      <ModelLibraryLinks />
    </div>
  );
}

function ModelTagHint({ cloud }: { cloud: boolean }) {
  return (
    <p className="text-xs text-muted-foreground">
      {cloud ? (
        <>
          <CloudDownload className="inline size-3 text-primary" /> Cloud-hosted — pulls
          instantly.
        </>
      ) : (
        <>This will download from the Ollama library. May be several GB.</>
      )}
    </p>
  );
}

function ModelLibraryLinks() {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
      <ModelLink href="https://ollama.com/search">Browse library</ModelLink>
      <ModelLink href="https://ollama.com/search?c=cloud">Browse cloud models</ModelLink>
      <ModelLink href="https://ollama.com/settings/keys">Get an API key</ModelLink>
    </div>
  );
}

function ModelLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 hover:text-foreground hover:underline"
    >
      {children}
      <ExternalLink className="size-3" />
    </a>
  );
}

function CloudBillingNotice() {
  return (
    <Alert>
      <Info />
      <AlertDescription className="text-[11px] leading-relaxed">
        Cloud models are billed by <span className="font-medium">Ollama</span>
        per their plan. This app is just a runner — like Claude Code Desktop — and
        doesn&apos;t meter usage. Manage your quota at{" "}
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
  );
}
