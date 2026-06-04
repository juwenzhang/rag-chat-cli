import {Box, Text, useStdout} from 'ink';
import React, {useEffect, useMemo, useRef} from 'react';

import {ApiClient} from './api/client';
import {ErrorBoundary} from './components/common/error-boundary';
import {StreamSpinner} from './components/common/spinner';
import {LoginScreen} from './components/auth/login-screen';
import {AppShell} from './components/layout/app-shell';
import {useAuthStore} from './store/auth-store';
import {palette} from './theme/palette';

// Side-effect imports to populate the command registry. The composer queries
// it on every keystroke, so registration must happen before any UI mounts.
// The order matters only insofar as it dictates `/help` listing order — both
// modules just call ``registerCommand``.
import './commands/registry';
import './commands/extras';

export function App(): React.ReactElement {
  const api = useMemo(() => new ApiClient(), []);
  const user = useAuthStore((s) => s.user);
  const bootstrapping = useAuthStore((s) => s.bootstrapping);
  const bootstrap = useAuthStore((s) => s.bootstrap);
  const {stdout} = useStdout();
  const previousAuthed = useRef<boolean | null>(null);

  useEffect(() => {
    bootstrap(api);
  }, [api, bootstrap]);

  // Whenever the *authenticated* boundary flips (logged in ↔ logged out)
  // we wipe the alt-screen buffer before the next tree mounts. Without
  // this, Ink's diff-renderer leaves the previous screen's tail behind
  // because the new tree (LoginScreen ≪ AppShell) is much shorter — you
  // see the old transcript above the freshly-rendered login card.
  useEffect(() => {
    if (bootstrapping) return;
    const isAuthed = user != null;
    if (previousAuthed.current !== null && previousAuthed.current !== isAuthed) {
      // ESC[2J = clear entire screen, ESC[H = move cursor to home.
      // ESC[3J also clears scrollback, but we already own the alt
      // buffer so 2J is enough.
      stdout?.write('\x1b[2J\x1b[H');
    }
    previousAuthed.current = isAuthed;
  }, [bootstrapping, user, stdout]);

  return (
    <ErrorBoundary>
      {bootstrapping ? (
        <Box padding={1}>
          <Text color={palette.muted}>
            <StreamSpinner label="warming up" />
          </Text>
        </Box>
      ) : user ? (
        <AppShell api={api} />
      ) : (
        <LoginScreen api={api} />
      )}
    </ErrorBoundary>
  );
}
