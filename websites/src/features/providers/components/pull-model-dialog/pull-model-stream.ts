import type { ProgressFrame } from "./pull-model-dialog-parts";

export async function readPullStream(
  response: Response,
  callbacks: {
    onProgress: (frame: ProgressFrame) => void;
    onDone: () => Promise<void>;
  }
) {
  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response stream");
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
      const event = parseSseFrame(frame);
      if (!event) continue;
      if (event.event === "progress") {
        callbacks.onProgress(event.data as ProgressFrame);
      } else if (event.event === "done") {
        await callbacks.onDone();
        return;
      } else if (event.event === "error") {
        throw new Error(
          (event.data as { message?: string }).message ?? "Pull failed"
        );
      }
    }
  }

  await callbacks.onDone();
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
