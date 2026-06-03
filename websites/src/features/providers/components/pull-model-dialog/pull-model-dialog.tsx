"use client";

import { useCallback, useRef, useState, type FormEvent } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import {
  PullModelConfirmStep,
  PullModelDoneStep,
  PullModelErrorStep,
  PullModelIdleForm,
  type ProgressFrame,
} from "./pull-model-dialog-parts";
import { PullModelProgress } from "./pull-model-progress";
import { readPullStream } from "./pull-model-stream";

interface Props {
  providerName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPullModel: (model: string, signal?: AbortSignal) => Promise<Response>;
  onSaveDescription?: (model: string, description: string | null) => Promise<unknown>;
  /** Called once a pull completes successfully so callers can refetch the model list. */
  onPulled?: (model: string) => void;
}

type Stage =
  | { kind: "idle" }
  | { kind: "confirm-local"; tag: string }
  | { kind: "pulling"; tag: string; isCloud: boolean; frame: ProgressFrame }
  | { kind: "done"; tag: string }
  | { kind: "error"; message: string; tag?: string };

/** Cloud-flagged tags pull near-instantly because no GB-sized layers download. */
function isCloudTag(tag: string): boolean {
  const normalized = tag.trim().toLowerCase();
  return normalized.endsWith(":cloud") || normalized.endsWith("-cloud");
}

export function PullModelDialog({
  providerName,
  open,
  onOpenChange,
  onPullModel,
  onSaveDescription,
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
        await onSaveDescription?.(modelTag, desc.trim());
      } catch {
        // Description save is non-fatal — pull already succeeded.
      }
    },
    [onSaveDescription]
  );

  const finishPull = useCallback(
    async (modelTag: string) => {
      setStage({ kind: "done", tag: modelTag });
      await saveDescription(modelTag, description);
      onPulled?.(modelTag);
    },
    [description, onPulled, saveDescription]
  );

  const startPull = useCallback(
    async (modelTag: string) => {
      const cloud = isCloudTag(modelTag);
      setStage({ kind: "pulling", tag: modelTag, isCloud: cloud, frame: {} });
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await onPullModel(modelTag, controller.signal);
        if (!response.body) throw new Error("No response stream");
        await readPullStream(response, {
          onProgress: (frame) => {
            setStage({ kind: "pulling", tag: modelTag, isCloud: cloud, frame });
          },
          onDone: async () => {
            await finishPull(modelTag);
            window.setTimeout(() => {
              onOpenChange(false);
              reset();
            }, 1200);
          },
        });
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
    [finishPull, onOpenChange, onPullModel, reset]
  );

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextTag = tag.trim();
    if (!nextTag) return;
    if (isCloudTag(nextTag)) {
      void startPull(nextTag);
    } else {
      setStage({ kind: "confirm-local", tag: nextTag });
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
            Downloads to <span className="font-mono text-foreground">{providerName}</span>
            . Tags ending in <span className="font-mono">:cloud</span> or{" "}
            <span className="font-mono">-cloud</span> are registered against Ollama Cloud
            and complete near-instantly.
          </DialogDescription>
        </DialogHeader>

        {stage.kind === "idle" && (
          <PullModelIdleForm
            tag={tag}
            description={description}
            isCloud={isCloudTag}
            onTagChange={setTag}
            onDescriptionChange={setDescription}
            onSubmit={onSubmit}
            onCancel={() => onOpenChange(false)}
          />
        )}

        {stage.kind === "confirm-local" && (
          <PullModelConfirmStep
            tag={stage.tag}
            onBack={() => setStage({ kind: "idle" })}
            onConfirm={() => void startPull(stage.tag)}
          />
        )}

        {stage.kind === "pulling" && (
          <PullModelProgress frame={stage.frame} tag={stage.tag} />
        )}

        {stage.kind === "done" && <PullModelDoneStep tag={stage.tag} />}

        {stage.kind === "error" && (
          <PullModelErrorStep
            message={stage.message}
            onClose={() => onOpenChange(false)}
            onRetry={() => {
              setTag(stage.tag ?? "");
              setStage({ kind: "idle" });
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
