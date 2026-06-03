"use client";

import { Loader2, Sparkles, Star } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { MessageEvaluationOut } from "@/lib/api/shared/types";
import { api } from "@/lib/api/browser";

export function EvaluationBlock({
  messageId,
  initial,
}: {
  messageId?: string;
  initial?: MessageEvaluationOut;
}) {
  const [evaluation, setEvaluation] = useState<MessageEvaluationOut | undefined>(initial);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!messageId || evaluation) return;
    let cancelled = false;
    api.chat
      .getMessageEvaluation(messageId)
      .then((next) => {
        if (!cancelled) setEvaluation(next);
      })
      .catch(() => {
        // 404 is expected before the user requests a score.
      });
    return () => {
      cancelled = true;
    };
  }, [evaluation, messageId]);

  const runEvaluation = async () => {
    if (!messageId || loading) return;
    setLoading(true);
    try {
      const next = await api.chat.evaluateMessage(messageId);
      setEvaluation(next);
    } catch (err) {
      toast.error((err as Error).message || "Failed to evaluate answer");
    } finally {
      setLoading(false);
    }
  };

  if (!messageId) return null;

  if (!evaluation) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={runEvaluation}
        disabled={loading}
        className="w-fit gap-1.5 text-xs"
      >
        {loading ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : (
          <Sparkles className="size-3.5" />
        )}
        AI score
      </Button>
    );
  }

  return (
    <div className="w-fit max-w-full rounded-lg border border-border bg-card px-3 py-2 text-xs text-muted-foreground">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="inline-flex items-center gap-1 font-medium text-foreground">
          <Star className="size-3.5 text-primary" />
          AI score {evaluation.overall}/5
        </span>
        <span>helpfulness {evaluation.helpfulness}/5</span>
        <span>grounding {evaluation.groundedness}/5</span>
        <span>citations {evaluation.citation_quality}/5</span>
        <span>complete {evaluation.completeness}/5</span>
        <span>risk {evaluation.risk}</span>
      </div>
      {evaluation.comment && (
        <p className="mt-1 whitespace-pre-wrap">{evaluation.comment}</p>
      )}
    </div>
  );
}
