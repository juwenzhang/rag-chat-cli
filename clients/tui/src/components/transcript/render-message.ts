import stripAnsi from 'strip-ansi';
import stringWidth from 'string-width';

import type {UIMessage} from '../../store/chat-store';
import {formatDuration, formatTokens} from '../../util/format';
import {renderMarkdown} from '../../markdown/render';

const COLOR = {
  user: '\u001b[36m',
  assistant: '\u001b[35m',
  system: '\u001b[33m',
  tool: '\u001b[34m',
  muted: '\u001b[2m',
  error: '\u001b[31m',
  warn: '\u001b[33m',
  reset: '\u001b[0m',
  bold: '\u001b[1m'
} as const;

const LABEL: Record<UIMessage['role'], string> = {
  user: 'you',
  assistant: 'asst',
  system: 'sys',
  tool: 'tool'
};

/**
 * Render one chat message into a flat list of terminal lines. Returning
 * `string[]` (instead of a React subtree) is what makes the transcript
 * scrollable line-by-line — once everything is a string we can slice
 * exactly `[start, start+height)` and never overflow the viewport.
 */
export function renderMessageLines(message: UIMessage, width: number): string[] {
  const lines: string[] = [];

  // header
  const color = COLOR[message.role];
  let header = `${color}${COLOR.bold}${LABEL[message.role]}${COLOR.reset}`;
  if (message.streaming) header += `${COLOR.muted} · streaming…${COLOR.reset}`;
  if (message.error) header += `${COLOR.error} · ${message.error}${COLOR.reset}`;
  if (!message.streaming && (message.durationMs || message.usage || message.model)) {
    const meta: string[] = [];
    if (message.durationMs) meta.push(formatDuration(message.durationMs));
    if (message.usage) {
      const tok = formatTokens(message.usage);
      if (tok) meta.push(tok);
    }
    if (message.model) meta.push(message.model);
    if (meta.length) header += `${COLOR.muted} · ${meta.join(' · ')}${COLOR.reset}`;
  }
  lines.push(header);

  // thoughts
  for (const text of message.thoughts) {
    for (const line of wrap(text, width - 4)) {
      lines.push(`${COLOR.muted}  · ${line}${COLOR.reset}`);
    }
  }

  // tool calls
  for (const call of message.toolCalls) {
    const args = safeJson(call.arguments, width - 8);
    lines.push(`${COLOR.tool}  ⚒ ${call.name}${COLOR.reset}${COLOR.muted} ${args}${COLOR.reset}`);
    const result = message.toolResults.find((r) => r.id === call.id);
    if (result) {
      const summary = oneLine(result.output, width - 8);
      const colorPick = result.error ? COLOR.error : COLOR.muted;
      lines.push(`${colorPick}    ↳ ${summary}${COLOR.reset}`);
    }
  }

  // body — markdown for assistant, plain for everyone else
  const body =
    message.role === 'assistant'
      ? renderMarkdown(message.content || (message.streaming ? ' ' : ' '), width)
      : message.content;
  for (const raw of body.split('\n')) {
    if (stringWidth(stripAnsi(raw)) <= width) {
      lines.push(raw);
    } else {
      // markdown render already wrapped at `width`; this is just a guard for
      // pathological inputs (URLs, base64) that don't have soft breaks.
      for (const piece of hardWrap(raw, width)) lines.push(piece);
    }
  }

  // sources
  if (message.sources && message.sources.length > 0) {
    lines.push('');
    lines.push(`${COLOR.muted}sources${COLOR.reset}`);
    for (const src of message.sources.slice(0, 5)) {
      const label = src.title ?? src.source ?? src.url ?? 'unknown';
      lines.push(`${COLOR.muted}  [${src.rank}] ${oneLine(label, width - 6)}${COLOR.reset}`);
    }
  }

  lines.push(''); // trailing gap between messages
  return lines;
}

function wrap(value: string, width: number): string[] {
  if (width <= 1) return [value];
  const out: string[] = [];
  let buffer = '';
  for (const word of value.split(/(\s+)/)) {
    const candidate = buffer + word;
    if (stringWidth(candidate) > width && buffer) {
      out.push(buffer.trimEnd());
      buffer = word.trimStart();
    } else {
      buffer = candidate;
    }
  }
  if (buffer) out.push(buffer);
  return out;
}

function hardWrap(value: string, width: number): string[] {
  const out: string[] = [];
  let buffer = '';
  let bufferWidth = 0;
  for (const ch of Array.from(value)) {
    const w = stringWidth(stripAnsi(ch));
    if (bufferWidth + w > width) {
      out.push(buffer);
      buffer = ch;
      bufferWidth = w;
    } else {
      buffer += ch;
      bufferWidth += w;
    }
  }
  if (buffer) out.push(buffer);
  return out;
}

function oneLine(value: string, max: number): string {
  const flat = value.replace(/\s+/g, ' ').trim();
  if (stringWidth(flat) <= max) return flat;
  return `${flat.slice(0, Math.max(0, max - 1))}…`;
}

function safeJson(value: unknown, max: number): string {
  let serialised: string;
  try {
    serialised = JSON.stringify(value);
  } catch {
    serialised = String(value);
  }
  return oneLine(serialised, max);
}
