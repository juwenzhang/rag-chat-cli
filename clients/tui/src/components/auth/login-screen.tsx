import {Box, Text, useInput} from 'ink';
import BigText from 'ink-big-text';
import Gradient from 'ink-gradient';
import TextInput from 'ink-text-input';
import React, {useState} from 'react';

import type {ApiClient} from '../../api/client';
import {ApiError} from '../../api/types';
import {useAuthStore} from '../../store/auth-store';
import {palette} from '../../theme/palette';
import {StreamSpinner} from '../common/spinner';

interface Props {
  api: ApiClient;
}

type Mode = 'login' | 'register';
type Field = 'email' | 'password' | 'displayName';

const LOGIN_FIELDS: Field[] = ['email', 'password'];
const REGISTER_FIELDS: Field[] = ['email', 'password', 'displayName'];

export function LoginScreen({api}: Props): React.ReactElement {
  const login = useAuthStore((s) => s.login);
  const logging = useAuthStore((s) => s.logging);
  const error = useAuthStore((s) => s.loginError);

  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [field, setField] = useState<Field>('email');
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const fields = mode === 'login' ? LOGIN_FIELDS : REGISTER_FIELDS;

  useInput((input, key) => {
    if (key.tab) {
      const idx = fields.indexOf(field);
      const next = key.shift
        ? fields[(idx - 1 + fields.length) % fields.length]
        : fields[(idx + 1) % fields.length];
      if (next) setField(next);
      return;
    }
    // Ctrl+S toggles between login / register modes (Ctrl+R clashes with the
    // composer's regenerate shortcut, so we use Ctrl+S = "switch").
    if (key.ctrl && (input === 's' || input === 'S')) {
      setMode((prev) => (prev === 'login' ? 'register' : 'login'));
      setField('email');
      setLocalError(null);
      setInfo(null);
    }
  });

  const submitLogin = async () => {
    if (!email.trim() || !password) return;
    setLocalError(null);
    setInfo(null);
    await login(api, email.trim(), password);
  };

  const submitRegister = async () => {
    if (!email.trim() || !password) return;
    setBusy(true);
    setLocalError(null);
    setInfo(null);
    try {
      await api.register(email.trim(), password, displayName.trim() || undefined);
      // Auto-login after a successful registration so the user lands directly
      // in the main shell (matches the website's UX).
      const ok = await login(api, email.trim(), password);
      if (!ok) {
        setMode('login');
        setInfo('account created — please sign in');
      }
    } catch (err) {
      const message =
        err instanceof ApiError
          ? `${err.code}: ${err.message}`
          : err instanceof Error
            ? err.message
            : 'register failed';
      setLocalError(message);
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = mode === 'login' ? submitLogin : submitRegister;
  const advance = (next: Field | null) => {
    if (next) setField(next);
    else void onSubmit();
  };

  const errorText = localError ?? error;
  const buttonLabel = mode === 'login' ? 'sign in' : 'create account';
  const switchHint =
    mode === 'login'
      ? 'Ctrl+S create account · Tab switch · Enter submit'
      : 'Ctrl+S back to sign in · Tab switch · Enter submit';

  return (
    <Box flexDirection="column" padding={1} alignItems="center">
      <Gradient name="pastel">
        <BigText text="lhx-rag" font="tiny" />
      </Gradient>
      <Box marginBottom={1}>
        <Text color={palette.muted}>Ink terminal client · API: {api.baseUrl}</Text>
      </Box>

      <Box
        flexDirection="column"
        width={60}
        borderStyle="round"
        borderColor={palette.border}
        padding={1}
      >
        <Text color={palette.accent} bold>
          {mode === 'login' ? 'Sign in' : 'Create account'}
        </Text>

        <Box marginTop={1}>
          <Box width={14}>
            <Text color={field === 'email' ? palette.accent : palette.muted}>email</Text>
          </Box>
          <TextInput
            value={email}
            onChange={setEmail}
            focus={field === 'email'}
            placeholder="you@example.com"
            onSubmit={() => advance('password')}
          />
        </Box>
        <Box>
          <Box width={14}>
            <Text color={field === 'password' ? palette.accent : palette.muted}>password</Text>
          </Box>
          <TextInput
            value={password}
            onChange={setPassword}
            focus={field === 'password'}
            mask="•"
            onSubmit={() => advance(mode === 'register' ? 'displayName' : null)}
          />
        </Box>
        {mode === 'register' ? (
          <Box>
            <Box width={14}>
              <Text color={field === 'displayName' ? palette.accent : palette.muted}>
                display name
              </Text>
            </Box>
            <TextInput
              value={displayName}
              onChange={setDisplayName}
              focus={field === 'displayName'}
              placeholder="optional"
              onSubmit={() => advance(null)}
            />
          </Box>
        ) : null}

        {errorText ? (
          <Box marginTop={1}>
            <Text color={palette.error}>{errorText}</Text>
          </Box>
        ) : null}
        {info ? (
          <Box marginTop={1}>
            <Text color={palette.accent}>{info}</Text>
          </Box>
        ) : null}

        <Box marginTop={1}>
          {logging || busy ? (
            <StreamSpinner label={busy ? 'creating account' : 'signing in'} />
          ) : (
            <Text color={palette.muted}>{buttonLabel} — {switchHint}</Text>
          )}
        </Box>
      </Box>
    </Box>
  );
}
