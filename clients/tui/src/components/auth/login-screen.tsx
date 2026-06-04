import {Box, Text, useInput} from 'ink';
import BigText from 'ink-big-text';
import Gradient from 'ink-gradient';
import TextInput from 'ink-text-input';
import React, {useState} from 'react';

import type {ApiClient} from '../../api/client';
import {useAuthStore} from '../../store/auth-store';
import {palette} from '../../theme/palette';
import {StreamSpinner} from '../common/spinner';

interface Props {
  api: ApiClient;
}

type Field = 'email' | 'password';

export function LoginScreen({api}: Props): React.ReactElement {
  const login = useAuthStore((s) => s.login);
  const logging = useAuthStore((s) => s.logging);
  const error = useAuthStore((s) => s.loginError);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [field, setField] = useState<Field>('email');

  useInput((input, key) => {
    if (key.tab) {
      setField((prev) => (prev === 'email' ? 'password' : 'email'));
      return;
    }
    if (key.shift && key.tab) {
      setField((prev) => (prev === 'email' ? 'password' : 'email'));
      return;
    }
    // ignore raw input — TextInput owns the chars for the focused field
    void input;
  });

  const submit = async () => {
    if (!email.trim() || !password) return;
    await login(api, email.trim(), password);
  };

  return (
    <Box flexDirection="column" padding={1} alignItems="center">
      <Gradient name="pastel">
        <BigText text="lhx-rag" font="tiny" />
      </Gradient>
      <Box marginBottom={1}>
        <Text color={palette.muted}>Ink terminal client · API: {api.baseUrl}</Text>
      </Box>

      <Box flexDirection="column" width={60} borderStyle="round" borderColor={palette.border} padding={1}>
        <Text color={palette.accent} bold>
          Sign in
        </Text>
        <Box marginTop={1}>
          <Box width={12}>
            <Text color={field === 'email' ? palette.accent : palette.muted}>email</Text>
          </Box>
          <TextInput
            value={email}
            onChange={setEmail}
            focus={field === 'email'}
            placeholder="you@example.com"
            onSubmit={() => setField('password')}
          />
        </Box>
        <Box>
          <Box width={12}>
            <Text color={field === 'password' ? palette.accent : palette.muted}>password</Text>
          </Box>
          <TextInput
            value={password}
            onChange={setPassword}
            focus={field === 'password'}
            mask="•"
            onSubmit={submit}
          />
        </Box>
        {error ? (
          <Box marginTop={1}>
            <Text color={palette.error}>{error}</Text>
          </Box>
        ) : null}
        <Box marginTop={1}>
          {logging ? (
            <StreamSpinner label="signing in" />
          ) : (
            <Text color={palette.muted}>Tab switch field · Enter submit · Ctrl+C exit</Text>
          )}
        </Box>
      </Box>
    </Box>
  );
}
