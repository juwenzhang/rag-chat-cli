import {Box, useApp, useInput} from 'ink';
import React, {useEffect} from 'react';

import type {ApiClient} from '../../api/client';
import {useChatStore} from '../../store/chat-store';
import {useSessionStore} from '../../store/session-store';
import {useUiStore} from '../../store/ui-store';
import {useWindowSize} from '../../hooks/use-window-size';
import {Composer} from '../composer/composer';
import {SessionList} from '../sessions/session-list';
import {Transcript} from '../transcript/transcript';
import {ToastStack} from '../common/toast-stack';
import {HelpPanel} from '../panels/help-panel';
import {Header} from './header';
import {StatusBar} from './status-bar';

interface Props {
  api: ApiClient;
}

const SIDEBAR_MIN = 24;
const SIDEBAR_RATIO = 0.22;

/**
 * Top-level chrome: header / three-pane body / composer / status.
 *
 * Three focusable panes (sessions, transcript, composer) cycle with Tab /
 * Shift+Tab. Pane-specific shortcuts (j/k for transcript scrolling, ↑/↓ for
 * session navigation, etc.) live in the matching `if (pane === …)` branch so
 * they never fire while another pane owns the focus.
 */
export function AppShell({api}: Props): React.ReactElement {
  const {columns, rows} = useWindowSize();
  const {exit} = useApp();

  const sessions = useSessionStore((s) => s.sessions);
  const activeId = useSessionStore((s) => s.activeId);
  const refreshSessions = useSessionStore((s) => s.refresh);
  const selectSession = useSessionStore((s) => s.select);
  const createSession = useSessionStore((s) => s.create);

  const loadSession = useChatStore((s) => s.loadSession);
  const regenerate = useChatStore((s) => s.regenerate);
  const stop = useChatStore((s) => s.stop);
  const streaming = useChatStore((s) => s.streaming);

  const overlay = useUiStore((s) => s.overlay);
  const setOverlay = useUiStore((s) => s.setOverlay);
  const pane = useUiStore((s) => s.pane);
  const cyclePane = useUiStore((s) => s.cyclePane);
  const commandPaletteOpen = useUiStore((s) => s.commandPaletteOpen);
  const setPane = useUiStore((s) => s.setPane);
  const followBottom = useUiStore((s) => s.followBottom);
  const scrollOffset = useUiStore((s) => s.scrollOffset);
  const setScrollOffset = useUiStore((s) => s.setScrollOffset);
  const setFollowBottom = useUiStore((s) => s.setFollowBottom);
  const pushToast = useUiStore((s) => s.pushToast);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await refreshSessions(api);
      if (cancelled) return;
      const first = useSessionStore.getState().activeId;
      if (first) await loadSession(api, first);
    })();
    return () => {
      cancelled = true;
    };
  }, [api, refreshSessions, loadSession]);

  useEffect(() => {
    if (!activeId) return;
    loadSession(api, activeId);
  }, [activeId, api, loadSession]);

  useInput((input, key) => {
    if (overlay) {
      if (key.escape) setOverlay(null);
      return;
    }

    // ── Pane cycling — Tab / Shift+Tab. The composer's slash-command
    //    palette also wants Tab (for completion), so defer to it when the
    //    palette is open.
    if (key.tab && !commandPaletteOpen) {
      cyclePane(key.shift ? -1 : 1);
      return;
    }

    // ── Global shortcuts (Ctrl-modified) ────────────────────────────────
    if (key.ctrl && input === 'c') {
      if (streaming) {
        stop();
        pushToast('ok', 'stop requested');
        return;
      }
      exit();
      return;
    }
    if (key.ctrl && input === 'n') {
      void (async () => {
        const created = await createSession(api, null);
        if (created) {
          await loadSession(api, created.id);
          pushToast('ok', 'new session');
        }
      })();
      return;
    }
    if (key.ctrl && input === 'p') {
      setPane('sessions');
      return;
    }
    if (key.ctrl && input === 'r') {
      if (!activeId) {
        pushToast('warn', 'no active session');
        return;
      }
      void regenerate(api, activeId);
      return;
    }

    // Escape always returns to "follow bottom" for the transcript.
    if (key.escape && !followBottom) {
      setFollowBottom(true);
      return;
    }

    // ── Pane-scoped shortcuts ───────────────────────────────────────────
    if (pane === 'sessions') {
      if (input === '?') {
        setOverlay('help');
        return;
      }
      const idx = sessions.findIndex((s) => s.id === activeId);
      if (key.upArrow || input === 'k') {
        const next = sessions[Math.max(0, idx - 1)];
        if (next) selectSession(next.id);
        return;
      }
      if (key.downArrow || input === 'j') {
        const next = sessions[Math.min(sessions.length - 1, idx + 1)];
        if (next) selectSession(next.id);
        return;
      }
      if (key.return) {
        setPane('composer');
        return;
      }
      return;
    }

    if (pane === 'transcript') {
      if (input === '?') {
        setOverlay('help');
        return;
      }
      if (key.upArrow || input === 'k') {
        setScrollOffset(scrollOffset + 1);
        return;
      }
      if (key.downArrow || input === 'j') {
        setScrollOffset(Math.max(0, scrollOffset - 1));
        return;
      }
      if (key.pageUp) {
        setScrollOffset(scrollOffset + 10);
        return;
      }
      if (key.pageDown) {
        setScrollOffset(Math.max(0, scrollOffset - 10));
        return;
      }
      if (input === 'g') {
        setScrollOffset(Number.MAX_SAFE_INTEGER);
        return;
      }
      if (input === 'G') {
        setFollowBottom(true);
        return;
      }
      if (key.return) {
        setPane('composer');
        return;
      }
      return;
    }

    // pane === 'composer'
    // PgUp/PgDn still scroll the transcript even from the composer so the
    // user doesn't have to leave the input to peek at history.
    if (key.pageUp) {
      setScrollOffset(scrollOffset + 10);
      return;
    }
    if (key.pageDown) {
      setScrollOffset(Math.max(0, scrollOffset - 10));
      return;
    }
  });

  const sidebarWidth = Math.max(SIDEBAR_MIN, Math.floor(columns * SIDEBAR_RATIO));
  const transcriptWidth = Math.max(40, columns - sidebarWidth - 2);
  // header(1) + composer box(3 incl. border) + composer hint row(1) +
  // status bar(1) = 6. Palette adds up to 8 rows when open (6 candidates +
  // header + border).
  const paletteRows = commandPaletteOpen ? 8 : 0;
  const bodyHeight = Math.max(6, rows - 6 - paletteRows);

  if (overlay === 'help') {
    return (
      <Box flexDirection="column" width={columns} height={rows}>
        <Header width={columns} />
        <Box flexGrow={1} paddingX={1}>
          <HelpPanel width={columns} />
        </Box>
        <StatusBar api={api} width={columns} />
      </Box>
    );
  }

  return (
    <Box flexDirection="column" width={columns} height={rows}>
      <Header width={columns} />
      <Box flexDirection="row" width={columns} height={bodyHeight}>
        <SessionList
          api={api}
          sessions={sessions}
          activeId={activeId}
          width={sidebarWidth}
          height={bodyHeight}
          focused={pane === 'sessions'}
        />
        <Transcript
          width={transcriptWidth}
          height={bodyHeight}
          focused={pane === 'transcript'}
        />
      </Box>
      <Composer api={api} width={columns} focused={pane === 'composer'} />
      <StatusBar api={api} width={columns} />
      <ToastStack />
    </Box>
  );
}
