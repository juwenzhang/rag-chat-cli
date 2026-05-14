"use client";

import type { UIMessage } from "../types";

import { ToolCallCard } from "./tool-call-card";

/** Stack of tool-call cards for one assistant turn, pairing each call
 *  with its result and a running/done/failed status. */
export function ToolCallsBlock({
  calls,
  results,
}: {
  calls: NonNullable<UIMessage["toolCalls"]>;
  results: NonNullable<UIMessage["toolResults"]>;
}) {
  return (
    <div className="flex flex-col gap-2">
      {calls.map((c) => {
        const result = results.find((r) => r.id === c.id);
        const status = result?.error
          ? "failed"
          : result
            ? "done"
            : "running";
        return (
          <ToolCallCard key={c.id} call={c} result={result} status={status} />
        );
      })}
    </div>
  );
}
