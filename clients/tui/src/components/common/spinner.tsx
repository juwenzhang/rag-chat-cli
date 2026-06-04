import {Text} from 'ink';
import Spinner from 'ink-spinner';
import React from 'react';

import {palette} from '../../theme/palette';

export function StreamSpinner({label}: {label?: string}): React.ReactElement {
  return (
    <Text>
      <Text color={palette.accent}>
        <Spinner type="dots" />
      </Text>
      {label ? <Text> {label}</Text> : null}
    </Text>
  );
}
