import {Box, Text} from 'ink';
import Gradient from 'ink-gradient';
import React from 'react';

import {palette} from '../../theme/palette';

interface Props {
  width: number;
}

export function Header({width}: Props): React.ReactElement {
  return (
    <Box width={width} paddingX={1}>
      <Gradient name="pastel">
        <Text bold>lhx-rag</Text>
      </Gradient>
      <Text color={palette.muted}> · API-only Ink terminal · /help</Text>
    </Box>
  );
}
