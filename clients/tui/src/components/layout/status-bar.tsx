import {Box, Text} from 'ink';
import React from 'react';

import type {ApiClient} from '../../api/client';
import {useChatStore} from '../../store/chat-store';
import {useSessionStore} from '../../store/session-store';
import {PANE_LABEL, useUiStore} from '../../store/ui-store';
import {palette} from '../../theme/palette';
import {truncate} from '../../util/format';

interface Props {
  api: ApiClient;
  width: number;
}

/**
 * One-line status footer.
 *
 * Identity (email) and connection (api base url) used to live here, but
 * they're better placed in the sessions sidebar footer where they don't
 * compete with the runtime-y bits. What remains:
 *
 *   left:  ⏵/· status · session title       — what is happening right now
 *   right: [pane] · model                     — where focus is, and the
 *                                              currently effective model
 */
export function StatusBar({api, width}: Props): React.ReactElement {
  const status = useUiStore((s) => s.status);
  const pane = useUiStore((s) => s.pane);
  const streaming = useChatStore((s) => s.streaming);
  const messages = useChatStore((s) => s.messages);
  const activeId = useSessionStore((s) => s.activeId);
  const sessions = useSessionStore((s) => s.sessions);

  const session = sessions.find((s) => s.id === activeId);

  // Pull the currently effective model from the most recent assistant
  // turn — the backend stamps `model` into the `done` event so this is
  // the authoritative source of "what just answered me". When no turn
  // has finished yet, fall back to the session's pinned model (if any).
  const recentAssistant = [...messages].reverse().find((m) => m.role === 'assistant');
  const effectiveModel = recentAssistant?.model ?? session?.model ?? null;

  const left = `${streaming ? '⏵' : '·'} ${status}${
    session ? ` · ${truncate(session.title ?? 'untitled', 24)}` : ''
  }`;

  // Quietly silence unused-variable lint until we wire something with the
  // api handle here (e.g. a connection indicator). Drop this when used.
  void api;

  return (
    <Box width={width} paddingX={1} justifyContent="space-between">
      <Text color={streaming ? palette.warn : palette.muted}>{left}</Text>
      <Box>
        <Text color={palette.accent} bold>
          [{PANE_LABEL[pane]}]
        </Text>
        {effectiveModel ? (
          <Text color={palette.muted}> · {truncate(effectiveModel, 32)}</Text>
        ) : null}
      </Box>
    </Box>
  );
}
