import stripAnsi from 'strip-ansi';
import stringWidth from 'string-width';

import {ErrorCode, MessageRole} from '../../api/enums';
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
  if (message.error) {
    const summary = formatErrorSummary(message.error);
    header += `${COLOR.error} · ${summary}${COLOR.reset}`;
  }
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

  // body — markdown for assistant, plain for everyone else.
  //
  // Defensive collapse: production sometimes stores the raw upstream error
  // body (Cloudflare 429 HTML, gateway pages, HTML-wrapped JSON) directly
  // inside ``messages.content`` because the LLM client surfaces upstream
  // failures verbatim. Rendering 200 lines of HTML through marked makes the
  // transcript unusable. We detect the pattern early and substitute a one-
  // line red badge instead.
  const collapsed = collapseUpstreamError(message.content);
  if (collapsed) {
    for (const piece of wrap(collapsed, width - 2)) {
      lines.push(`${COLOR.error}${piece}${COLOR.reset}`);
    }
  } else {
    const body =
      message.role === MessageRole.Assistant
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

/**
 * Detect upstream-error payloads that leaked into ``messages.content`` and
 * return a one-line summary (without the HTML body). Returns ``null`` when
 * the content looks like a normal answer.
 *
 * Patterns we collapse:
 *   - ``<provider> /<endpoint> failed: <code> '<html-or-json>'`` (our own
 *     wrapper around upstream errors — the leading text is already a clean
 *     summary, we just drop the embedded body).
 *   - Bare HTML responses (``<!doctype`` / ``<html``) — these come from
 *     CDN / WAF intercepts and never carry useful prose.
 */
function collapseUpstreamError(raw: string): string | null {
  const trimmed = raw.trimStart();
  if (!trimmed) return null;

  // Pattern 1: "ollama /api/chat failed: 429 '<!doctype html>...'"
  const wrapped = trimmed.match(
    /^([^\n']{1,200}?failed:\s*\d{3})\s*'<\s*(?:!doctype|html|\?xml)/i
  );
  if (wrapped) {
    return `${wrapped[1]} (upstream returned an HTML error page; full body hidden)`;
  }

  // Pattern 2: bare HTML page — keep it short, drop the markup.
  if (/^<\s*(?:!doctype|html|\?xml)/i.test(trimmed)) {
    return 'upstream returned an HTML error page (full body hidden)';
  }

  // Pattern 3: ``Error: ...`` + an embedded JSON / HTML blob longer than
  // ~400 chars on a single line — collapse to the prefix.
  if (/^(?:Error|RequestError|HTTPError):/i.test(trimmed)) {
    const firstLine = trimmed.split('\n', 1)[0] ?? trimmed;
    if (firstLine.length > 200) {
      return `${firstLine.slice(0, 180)}… (truncated)`;
    }
  }
  return null;
}

/**
 * Build a short header summary for an :class:`ErrorPayload`. We branch on
 * ``code`` instead of grepping ``message`` so the prompt stays stable
 * across upstream wording changes. Code dictionary in
 * ``docs/backend/ERROR_CODES.md``.
 */
function formatErrorSummary(error: {
  code: string;
  message: string;
  retry_after?: number | null;
  upstream_url?: string | null;
}): string {
  switch (error.code) {
    case ErrorCode.LlmSubscriptionRequired:
      return 'subscription required (open ollama.com/upgrade)';
    case ErrorCode.LlmRateLimited:
      return error.retry_after
        ? `rate limited (retry in ~${error.retry_after}s)`
        : 'rate limited';
    case ErrorCode.LlmUnauthorized:
      return 'provider rejected the API key';
    case ErrorCode.LlmModelNotFound:
      return 'model not available upstream';
    case ErrorCode.LlmUpstreamUnavailable:
      return 'upstream unavailable';
    case ErrorCode.Aborted:
      return 'aborted';
    default:
      return error.message || error.code;
  }
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
