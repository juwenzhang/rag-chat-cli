import {Box, Text} from 'ink';
import React from 'react';

import type {CommandSpec} from '../../commands/types';
import {palette} from '../../theme/palette';
import {fitToWidth} from '../../util/ansi-line';

interface Props {
  candidates: CommandSpec[];
  highlight: number;
  width: number;
}

const VISIBLE = 6;

/**
 * Floating completion list rendered just above the input box.
 *
 * Ink does not support real overlays/z-index so we paint a fully opaque block
 * (every row is padded to the viewport width with inverse video) to keep the
 * transcript text behind the palette from bleeding through.
 *
 * The visible slice is computed from `highlight` so moving past the bottom of
 * the window scrolls the list — without this the user could press ↓ forever
 * with no visual change, which is what made it look like the picker was
 * stuck.
 */
export function CommandHint({candidates, highlight, width}: Props): React.ReactElement | null {
  if (candidates.length === 0) return null;

  // -4 = round border (2) + paddingX 1 each side.
  const innerWidth = Math.max(20, width - 4);
  const total = candidates.length;
  const windowSize = Math.min(VISIBLE, total);
  // Keep the highlighted row inside the window. When we're at the very end
  // we clamp so the window doesn't slide past the last candidate.
  const start = Math.max(0, Math.min(highlight - Math.floor(windowSize / 2), total - windowSize));
  const slice = candidates.slice(start, start + windowSize);

  const hiddenAbove = start;
  const hiddenBelow = total - (start + windowSize);

  return (
    <Box
      flexDirection="column"
      width={width}
      borderStyle="round"
      borderColor={palette.borderFocus}
      paddingX={1}
    >
      <Text inverse color={palette.accent} bold>
        {fitToWidth(
          ` slash commands · ↑/↓ choose · Tab insert · Esc cancel · ${highlight + 1}/${total}`,
          innerWidth
        )}
      </Text>
      {hiddenAbove > 0 ? (
        <Text inverse color={palette.muted}>
          {fitToWidth(`  ↑ ${hiddenAbove} more`, innerWidth)}
        </Text>
      ) : null}
      {slice.map((spec, idx) => {
        const realIdx = start + idx;
        const active = realIdx === highlight;
        const line = `${active ? '▸ ' : '  '}/${spec.name}${spec.aliases?.length ? `  (${spec.aliases.join(', ')})` : ''}  — ${spec.description}`;
        return (
          <Text key={spec.name} inverse={active} color={active ? palette.accent : palette.text}>
            {fitToWidth(line, innerWidth)}
          </Text>
        );
      })}
      {hiddenBelow > 0 ? (
        <Text inverse color={palette.muted}>
          {fitToWidth(`  ↓ ${hiddenBelow} more`, innerWidth)}
        </Text>
      ) : null}
    </Box>
  );
}
