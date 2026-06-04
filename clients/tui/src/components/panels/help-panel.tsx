import {Box, Text} from 'ink';
import React, {useMemo} from 'react';

import {listCommands} from '../../commands/registry';
import type {CommandSpec} from '../../commands/types';
import {palette} from '../../theme/palette';

const ORDER: Array<CommandSpec['category']> = [
  'session',
  'chat',
  'rag',
  'knowledge',
  'config',
  'auth',
  'misc'
];
const LABEL: Record<CommandSpec['category'], string> = {
  session: 'session',
  chat: 'chat',
  rag: 'rag / think',
  knowledge: 'knowledge base',
  config: 'providers / preferences',
  auth: 'auth',
  misc: 'misc'
};

export function HelpPanel({width}: {width: number}): React.ReactElement {
  const grouped = useMemo(() => {
    const map = new Map<CommandSpec['category'], CommandSpec[]>();
    for (const spec of listCommands()) {
      const list = map.get(spec.category) ?? [];
      list.push(spec);
      map.set(spec.category, list);
    }
    for (const list of map.values()) list.sort((a, b) => a.name.localeCompare(b.name));
    return map;
  }, []);

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={palette.borderFocus}
      width={Math.min(80, width - 4)}
      paddingX={1}
    >
      <Text color={palette.accent} bold>
        commands · Esc to close
      </Text>
      {ORDER.map((cat) => {
        const list = grouped.get(cat);
        if (!list || list.length === 0) return null;
        return (
          <Box key={cat} flexDirection="column" marginTop={1}>
            <Text color={palette.muted} bold>
              {LABEL[cat]}
            </Text>
            {list.map((spec) => (
              <Text key={spec.name}>
                <Text color={palette.accent}>/{spec.name}</Text>
                {spec.aliases?.length ? (
                  <Text color={palette.muted}> ({spec.aliases.join(', ')})</Text>
                ) : null}
                <Text color={palette.muted}> — {spec.description}</Text>
              </Text>
            ))}
          </Box>
        );
      })}
      <Box marginTop={1}>
        <Text color={palette.muted}>
          keys: Tab pane · Ctrl+N new · Ctrl+R regenerate · Ctrl+C stop/exit · PgUp/PgDn scroll
        </Text>
      </Box>
    </Box>
  );
}
