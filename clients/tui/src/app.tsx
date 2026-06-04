import {Box, Text} from 'ink';
import React, {useEffect, useMemo} from 'react';

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

  useEffect(() => {
    bootstrap(api);
  }, [api, bootstrap]);

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
