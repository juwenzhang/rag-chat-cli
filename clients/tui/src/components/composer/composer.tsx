import {Box, Text, useInput} from 'ink';
import TextInput from 'ink-text-input';
import React, {useCallback, useEffect, useMemo, useState} from 'react';

import type {ApiClient} from '../../api/client';
import {parseCommand, suggestCommands, listCommands} from '../../commands/registry';
import type {CommandSpec} from '../../commands/types';
import {useChatStore} from '../../store/chat-store';
import {useSessionStore} from '../../store/session-store';
import {useUiStore} from '../../store/ui-store';
import {palette} from '../../theme/palette';
import {CommandHint} from './command-hint';

interface Props {
  api: ApiClient;
  width: number;
  focused: boolean;
}

const HISTORY_LIMIT = 50;

export function Composer({api, width, focused}: Props): React.ReactElement {
  const [value, setValue] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [historyCursor, setHistoryCursor] = useState<number | null>(null);
  const [hintIdx, setHintIdx] = useState(0);

  const streaming = useChatStore((s) => s.streaming);
  const send = useChatStore((s) => s.send);
  const stop = useChatStore((s) => s.stop);
  const useRag = useChatStore((s) => s.useRag);
  const thinkMode = useChatStore((s) => s.thinkMode);
  const activeId = useSessionStore((s) => s.activeId);
  const overlay = useUiStore((s) => s.overlay);
  const setOverlay = useUiStore((s) => s.setOverlay);
  const pushToast = useUiStore((s) => s.pushToast);
  const setStatus = useUiStore((s) => s.setStatus);
  const setCommandPaletteOpen = useUiStore((s) => s.setCommandPaletteOpen);

  const candidates = useMemo<CommandSpec[]>(() => {
    if (!value.startsWith('/')) return [];
    return suggestCommands(value);
  }, [value]);

  const paletteOpen = focused && !streaming && candidates.length > 0;

  // Mirror palette visibility into the global UI store so app-shell can
  // suppress its Tab-cycles-pane handler while completion is showing.
  useEffect(() => {
    setCommandPaletteOpen(paletteOpen);
    return () => {
      setCommandPaletteOpen(false);
    };
  }, [paletteOpen, setCommandPaletteOpen]);

  // Clamp the highlight if the candidate list shrank.
  useEffect(() => {
    if (hintIdx >= candidates.length) setHintIdx(0);
  }, [candidates.length, hintIdx]);

  const submit = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text) return;
      setValue('');
      setHistoryCursor(null);
      setHistory((prev) => {
        const next = [...prev.filter((entry) => entry !== text), text];
        return next.slice(-HISTORY_LIMIT);
      });

      if (text.startsWith('/')) {
        const parsed = parseCommand(text);
        if (!parsed) {
          pushToast('warn', `unknown command: ${text}`);
          return;
        }
        await parsed.spec.run({
          api,
          args: parsed.ctx.args,
          raw: parsed.ctx.raw,
          notify: pushToast,
          setStatus
        });
        return;
      }

      if (!activeId) {
        pushToast('warn', 'no active session — /new');
        return;
      }
      await send(api, activeId, text);
    },
    [api, activeId, pushToast, send, setStatus]
  );

  useInput(
    (input, key) => {
      if (overlay) {
        // overlays have their own dismiss handling, but Esc/closing keys go
        // straight back to closing the overlay so we don't fight focus.
        if (key.escape) setOverlay(null);
        return;
      }

      if (streaming && (key.ctrl && input === 'c')) {
        stop();
        pushToast('ok', 'stop requested');
        return;
      }

      if (paletteOpen) {
        if (key.upArrow) {
          setHintIdx((idx) => (idx - 1 + candidates.length) % candidates.length);
          return;
        }
        if (key.downArrow) {
          setHintIdx((idx) => (idx + 1) % candidates.length);
          return;
        }
        if (key.tab) {
          const pick = candidates[hintIdx];
          if (pick) {
            setValue(`/${pick.name} `);
            setHintIdx(0);
          }
          return;
        }
        if (key.escape) {
          setValue('');
          return;
        }
      } else if (history.length > 0) {
        if (key.upArrow) {
          const next = historyCursor === null ? history.length - 1 : Math.max(0, historyCursor - 1);
          setHistoryCursor(next);
          setValue(history[next] ?? '');
          return;
        }
        if (key.downArrow) {
          if (historyCursor === null) return;
          const next = historyCursor + 1;
          if (next >= history.length) {
            setHistoryCursor(null);
            setValue('');
          } else {
            setHistoryCursor(next);
            setValue(history[next] ?? '');
          }
          return;
        }
      }
    },
    {isActive: focused}
  );

  const innerWidth = Math.max(20, width - 4);

  const prompt = streaming ? '… ' : focused ? '› ' : '· ';
  const placeholder = !focused
    ? 'Tab to focus composer'
    : streaming
      ? 'streaming — Ctrl+C to stop'
      : 'message or /command';

  return (
    <Box flexDirection="column" width={width}>
      {paletteOpen ? (
        <CommandHint candidates={candidates} highlight={hintIdx} width={width} />
      ) : null}
      <Box
        borderStyle="round"
        borderColor={focused ? palette.borderFocus : palette.border}
        paddingX={1}
        width={width}
      >
        <Text color={streaming ? palette.warn : focused ? palette.accent : palette.muted}>
          {focused ? '● ' : '○ '}
          {prompt}
        </Text>
        <Box width={innerWidth}>
          <TextInput
            value={value}
            onChange={setValue}
            focus={focused && !streaming}
            placeholder={placeholder}
            onSubmit={submit}
          />
        </Box>
      </Box>
      <Box paddingX={1}>
        <Text color={palette.muted}>
          rag:{useRag ? 'on' : 'off'} · think:{formatThink(thinkMode)} · Tab/Shift+Tab pane · ↑/↓ history · /help
        </Text>
      </Box>
    </Box>
  );
}

function formatThink(value: boolean | 'low' | 'medium' | 'high'): string {
  if (value === true) return 'on';
  if (value === false) return 'off';
  return value;
}

// Re-exported here so app.tsx can pre-warm the registry import without a
// dedicated barrel file.
export const ALL_COMMANDS = listCommands;
