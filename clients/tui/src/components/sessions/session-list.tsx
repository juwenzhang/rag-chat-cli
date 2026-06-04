import {Box, Text} from 'ink';
import React from 'react';

import type {SessionMeta} from '../../api/types';
import {relativeTime, truncate} from '../../util/format';
import {palette} from '../../theme/palette';

interface Props {
  sessions: SessionMeta[];
  activeId: string | null;
  width: number;
  height: number;
  focused: boolean;
}

/**
 * Compact left-rail session list. We slice around the active session so
 * extremely long lists still show context without paying for virtualisation.
 */
export function SessionList({sessions, activeId, width, height, focused}: Props): React.ReactElement {
  const visible = Math.max(3, height - 2);
  const activeIdx = Math.max(0, sessions.findIndex((s) => s.id === activeId));
  const start = Math.max(0, Math.min(activeIdx - Math.floor(visible / 2), sessions.length - visible));
  const slice = sessions.slice(start, start + visible);

  return (
    <Box
      flexDirection="column"
      width={width}
      height={height}
      borderStyle="round"
      borderColor={focused ? palette.borderFocus : palette.border}
      paddingX={1}
    >
      <Text color={focused ? palette.accent : palette.muted} bold>
        {focused ? '● ' : '○ '}sessions ({sessions.length})
      </Text>
      {sessions.length === 0 ? (
        <Box marginTop={1}>
          <Text color={palette.muted}>no sessions yet — /new</Text>
        </Box>
      ) : null}
      <Box flexDirection="column" marginTop={1}>
        {slice.map((session) => {
          const isActive = session.id === activeId;
          const title = session.title?.trim() || `(untitled ${session.id.slice(0, 6)})`;
          return (
            <Box key={session.id} flexDirection="column">
              <Text color={isActive ? palette.accent : palette.text} bold={isActive}>
                {isActive ? '▸ ' : '  '}
                {truncate(title, Math.max(8, width - 6))}
              </Text>
              <Text color={palette.muted}>
                {'  '}
                {session.message_count ?? 0} msg · {relativeTime(session.updated_at || session.created_at)}
              </Text>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
