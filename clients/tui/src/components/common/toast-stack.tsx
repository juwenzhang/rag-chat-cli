import {Box, Text} from 'ink';
import React from 'react';

import {useUiStore} from '../../store/ui-store';
import {palette} from '../../theme/palette';

const COLOR: Record<string, string> = {
  info: palette.accent,
  warn: palette.warn,
  error: palette.error,
  ok: palette.ok
};

export function ToastStack(): React.ReactElement | null {
  const toasts = useUiStore((s) => s.toasts);
  if (toasts.length === 0) return null;
  return (
    <Box flexDirection="column" paddingX={1}>
      {toasts.map((toast) => (
        <Text key={toast.id} color={COLOR[toast.level] ?? palette.muted}>
          {toast.level.toUpperCase()} · {toast.message}
        </Text>
      ))}
    </Box>
  );
}
