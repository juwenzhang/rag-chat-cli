/**
 * Browser-side SSE parser. Consumes a Response.body and yields typed events
 * matching the FastAPI vocabulary (see core/streaming/events.py and
 * src/lib/api/types.ts).
 *
 * Pure ESM, no dependencies — works in client components and edge runtimes.
 */

import type { StreamEvent } from "@/lib/api/types";

function parseFrame(frame: string): StreamEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith(":")) continue;
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  const raw = dataLines.join("\n");
  try {
    return { type: event, data: JSON.parse(raw) } as StreamEvent;
  } catch {
    return { type: "error", data: { code: "PARSE", message: raw } };
  }
}

export async function* readSse(
  response: Response,
  signal?: AbortSignal
): AsyncGenerator<StreamEvent, void, unknown> {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const onAbort = () => reader.cancel().catch(() => undefined);
  signal?.addEventListener("abort", onAbort);

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const parsed = parseFrame(frame);
        if (parsed) yield parsed;
      }
    }
    if (buffer.trim()) {
      const parsed = parseFrame(buffer);
      if (parsed) yield parsed;
    }
  } finally {
    signal?.removeEventListener("abort", onAbort);
    reader.releaseLock();
  }
}
