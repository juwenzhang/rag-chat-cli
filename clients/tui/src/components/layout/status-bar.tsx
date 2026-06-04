import {Box, Text} from 'ink';
import React from 'react';

import type {ApiClient} from '../../api/client';
import {useAuthStore} from '../../store/auth-store';
import {useChatStore} from '../../store/chat-store';
import {useSessionStore} from '../../store/session-store';
import {PANE_LABEL, useUiStore} from '../../store/ui-store';
import {palette} from '../../theme/palette';
import {truncate} from '../../util/format';

interface Props {
  api: ApiClient;
  width: number;
}

export function StatusBar({api, width}: Props): React.ReactElement {
  const user = useAuthStore((s) => s.user);
  const status = useUiStore((s) => s.status);
  const pane = useUiStore((s) => s.pane);
  const streaming = useChatStore((s) => s.streaming);
  const activeId = useSessionStore((s) => s.activeId);
  const sessions = useSessionStore((s) => s.sessions);

  const session = sessions.find((s) => s.id === activeId);
  const right = `${user?.email ?? 'anon'} · ${api.baseUrl}`;
  const left = `${streaming ? '⏵' : '·'} ${status}${session ? ` · ${truncate(session.title ?? 'untitled', 24)}` : ''}`;

  return (
    <Box width={width} paddingX={1} justifyContent="space-between">
      <Text color={streaming ? palette.warn : palette.muted}>{left}</Text>
      <Box>
        <Text color={palette.accent} bold>
          [{PANE_LABEL[pane]}]
        </Text>
        <Text color={palette.muted}> · {right}</Text>
      </Box>
    </Box>
  );
}
