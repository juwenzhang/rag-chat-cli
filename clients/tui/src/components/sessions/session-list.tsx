import {Box, Text} from 'ink';
import React, {useEffect} from 'react';

import type {ApiClient} from '../../api/client';
import type {SessionMeta} from '../../api/types';
import {useAuthStore} from '../../store/auth-store';
import {useChatStore} from '../../store/chat-store';
import {useProviderStore} from '../../store/provider-store';
import {relativeTime, truncate} from '../../util/format';
import {palette} from '../../theme/palette';

interface Props {
  sessions: SessionMeta[];
  activeId: string | null;
  width: number;
  height: number;
  focused: boolean;
  api: ApiClient;
}

/**
 * Compact left-rail session list with a "footer card" pinned to the bottom.
 *
 * Layout:
 *   ┌─ sessions (N) ─────────┐
 *   │ ▸ active session       │
 *   │   2 msg · 5m ago       │   ← scrollable list (slice around active)
 *   │   …                     │
 *   ├─────────────────────────┤
 *   │ user@host               │
 *   │ http://api.example      │   ← identity / connection footer
 *   │ qwen3-coder-next:cloud  │
 *   │ provider: local-ollama  │
 *   └─────────────────────────┘
 *
 * The footer is non-focusable, just informational. We carve a fixed number
 * of rows out of the bottom and let the list breathe in whatever's left.
 */
const FOOTER_ROWS = 5; // 1 separator + up to 4 lines

export function SessionList({
  sessions,
  activeId,
  width,
  height,
  focused,
  api
}: Props): React.ReactElement {
  const user = useAuthStore((s) => s.user);
  const useRag = useChatStore((s) => s.useRag);
  const thinkMode = useChatStore((s) => s.thinkMode);
  const providers = useProviderStore((s) => s.providers);
  const ensureProviders = useProviderStore((s) => s.ensureLoaded);

  // Warm the provider cache once and refresh every minute so the footer's
  // provider name stays accurate after `/providers add` / `/providers rm`.
  useEffect(() => {
    void ensureProviders(api);
    const id = setInterval(() => void ensureProviders(api), 60_000);
    return () => clearInterval(id);
  }, [api, ensureProviders]);

  const activeSession = sessions.find((s) => s.id === activeId);
  const activeProvider = activeSession?.provider_id
    ? providers.find((p) => p.id === activeSession.provider_id)
    : providers.find((p) => p.is_default);

  // Reserve room for the footer; the list itself occupies whatever's left.
  const listHeight = Math.max(3, height - FOOTER_ROWS - 2 /* border + title */);
  const visible = Math.max(3, listHeight);
  const activeIdx = Math.max(0, sessions.findIndex((s) => s.id === activeId));
  const start = Math.max(
    0,
    Math.min(activeIdx - Math.floor(visible / 2), sessions.length - visible)
  );
  const slice = sessions.slice(start, start + visible);

  const innerWidth = Math.max(8, width - 4);

  const modelLabel = activeSession?.model
    ? truncate(activeSession.model, innerWidth)
    : 'model: ∅ (env / pref)';
  // Prefer the human-readable provider name from the cache; fall back to the
  // session's pinned id prefix while the cache is still warming up.
  const providerName =
    activeProvider?.name ??
    (activeSession?.provider_id ? activeSession.provider_id.slice(0, 8) : 'default');
  const providerLabel = `provider: ${providerName}${
    activeProvider && !activeSession?.provider_id ? ' (default)' : ''
  }`;
  const apiHost = formatHost(api.baseUrl);
  const userLabel = user?.email
    ? truncate(user.email, innerWidth)
    : 'anon';
  const flagsLabel = `rag:${useRag ? 'on' : 'off'} · think:${formatThink(thinkMode)}`;

  return (
    <Box
      flexDirection="column"
      width={width}
      height={height}
      borderStyle="round"
      borderColor={focused ? palette.borderFocus : palette.border}
      paddingX={1}
    >
      <Text color={focused ? palette.accent : palette.muted} bold>
        {focused ? '● ' : '○ '}sessions ({sessions.length})
      </Text>

      {sessions.length === 0 ? (
        <Box marginTop={1}>
          <Text color={palette.muted}>no sessions yet — /new</Text>
        </Box>
      ) : null}

      <Box flexDirection="column" marginTop={1} flexGrow={1}>
        {slice.map((session) => {
          const isActive = session.id === activeId;
          const title = session.title?.trim() || `(untitled ${session.id.slice(0, 6)})`;
          return (
            <Box key={session.id} flexDirection="column">
              <Text color={isActive ? palette.accent : palette.text} bold={isActive}>
                {isActive ? '▸ ' : '  '}
                {truncate(title, Math.max(8, width - 6))}
              </Text>
              <Text color={palette.muted}>
                {'  '}
                {session.message_count ?? 0} msg ·{' '}
                {relativeTime(session.updated_at || session.created_at)}
              </Text>
            </Box>
          );
        })}
      </Box>

      {/* Footer card — identity + connection + active model */}
      <Box flexDirection="column" marginTop={1}>
        <Text color={palette.border}>{'─'.repeat(innerWidth)}</Text>
        <Text color={palette.muted}>{userLabel}</Text>
        <Text color={palette.muted}>{truncate(apiHost, innerWidth)}</Text>
        <Text color={palette.accent} bold>
          {modelLabel}
        </Text>
        <Text color={palette.muted}>{truncate(providerLabel, innerWidth)}</Text>
        <Text color={palette.muted}>{flagsLabel}</Text>
      </Box>
    </Box>
  );
}

function formatThink(value: boolean | 'low' | 'medium' | 'high'): string {
  if (value === true) return 'on';
  if (value === false) return 'off';
  return value;
}

/**
 * Strip the protocol so the sidebar shows ``api.example.com`` instead of
 * ``https://api.example.com``. Falls back to the raw value on parse error.
 */
function formatHost(rawUrl: string): string {
  try {
    const url = new URL(rawUrl);
    return url.host + (url.pathname && url.pathname !== '/' ? url.pathname : '');
  } catch {
    return rawUrl;
  }
}
