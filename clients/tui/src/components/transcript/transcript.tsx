import {Box, Text} from 'ink';
import React, {useMemo} from 'react';

import {useChatStore} from '../../store/chat-store';
import {useUiStore} from '../../store/ui-store';
import {palette} from '../../theme/palette';
import {fitToWidth} from '../../util/ansi-line';
import {renderMessageLines} from './render-message';

interface Props {
  width: number;
  height: number;
  focused: boolean;
}

/**
 * Line-precise scrollable transcript.
 *
 * We pre-render every message into ANSI strings, concatenate, then slice to
 * the viewport. Each visible line is rendered as its own `<Text>` element at
 * an exact visual width — that's what keeps Ink from re-flowing CJK + ANSI
 * payloads and busting the bordered box.
 */
export function Transcript({width, height, focused}: Props): React.ReactElement {
  const messages = useChatStore((s) => s.messages);
  const loading = useChatStore((s) => s.loading);
  const followBottom = useUiStore((s) => s.followBottom);
  const scrollOffset = useUiStore((s) => s.scrollOffset);

  // border + paddingX(=1 each side) eats 4 cols; header eats 1 row.
  const innerWidth = Math.max(20, width - 4);
  const viewport = Math.max(3, height - 3);

  const lines = useMemo(() => {
    const out: string[] = [];
    for (const message of messages) {
      const block = renderMessageLines(message, innerWidth);
      for (const line of block) out.push(line);
    }
    return out;
  }, [messages, innerWidth]);

  const total = lines.length;
  const maxOffset = Math.max(0, total - viewport);
  const offset = followBottom ? 0 : Math.min(scrollOffset, maxOffset);
  const end = total - offset;
  const start = Math.max(0, end - viewport);
  const visible = lines.slice(start, end);
  while (visible.length < viewport) visible.push('');

  return (
    <Box
      flexDirection="column"
      width={width}
      height={height}
      borderStyle="round"
      borderColor={focused ? palette.borderFocus : palette.border}
      paddingX={1}
    >
      <Box>
        <Text color={focused ? palette.accent : palette.muted} bold>
          {focused ? '● ' : '○ '}transcript
        </Text>
        {!followBottom ? (
          <Text color={palette.warn}>
            {' '}
            · paused {start + 1}-{end}/{total} (Esc to follow)
          </Text>
        ) : null}
        {loading ? <Text color={palette.muted}> · loading…</Text> : null}
        {focused ? (
          <Text color={palette.muted}> · j/k PgUp/PgDn g/G</Text>
        ) : null}
      </Box>
      <Box flexDirection="column" height={viewport}>
        {messages.length === 0 ? (
          <Text color={palette.muted}>start a conversation — type below or /help</Text>
        ) : (
          visible.slice(0, viewport).map((line, idx) => (
            <Text key={idx}>{fitToWidth(line, innerWidth)}</Text>
          ))
        )}
      </Box>
    </Box>
  );
}
