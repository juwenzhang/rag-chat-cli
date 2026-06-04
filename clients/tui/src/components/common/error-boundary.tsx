import {Box, Text} from 'ink';
import React from 'react';

interface State {
  error: Error | null;
}

/**
 * Render-time errors otherwise crash the entire Ink tree. Catching them lets
 * the user see what blew up and run /quit cleanly instead of staring at a
 * silent terminal.
 */
export class ErrorBoundary extends React.Component<{children: React.ReactNode}, State> {
  override state: State = {error: null};

  static getDerivedStateFromError(error: Error): State {
    return {error};
  }

  override componentDidCatch(error: Error): void {
    // best-effort surface the trace so DEBUG=1 captures it
    if (process.env['DEBUG'] === '1') {
      // eslint-disable-next-line no-console
      console.error(error);
    }
  }

  override render(): React.ReactNode {
    if (this.state.error) {
      return (
        <Box flexDirection="column" padding={1} borderStyle="round" borderColor="red">
          <Text color="red" bold>
            lhx-rag crashed
          </Text>
          <Text>{this.state.error.message}</Text>
          <Text dimColor>set DEBUG=1 for stack traces in ~/.config/lhx-rag/debug.log</Text>
        </Box>
      );
    }
    return this.props.children;
  }
}
