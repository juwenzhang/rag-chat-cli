import {distance} from 'fastest-levenshtein';

import {useChatStore} from '../store/chat-store';
import {useProviderStore} from '../store/provider-store';
import {useSessionStore} from '../store/session-store';
import {useUiStore} from '../store/ui-store';
import {useAuthStore} from '../store/auth-store';
import type {CommandCtx, CommandSpec} from './types';

const commands: CommandSpec[] = [];
const byName = new Map<string, CommandSpec>();

export function registerCommand(spec: CommandSpec): void {
  commands.push(spec);
  byName.set(spec.name.toLowerCase(), spec);
  for (const alias of spec.aliases ?? []) byName.set(alias.toLowerCase(), spec);
}

export function listCommands(): CommandSpec[] {
  return [...commands];
}

export function findCommand(name: string): CommandSpec | undefined {
  return byName.get(name.toLowerCase());
}

export function suggestCommands(prefix: string): CommandSpec[] {
  const needle = prefix.toLowerCase().replace(/^\//, '');
  if (!needle) return [...commands];
  const exact = commands.filter((spec) => spec.name.startsWith(needle));
  if (exact.length > 0) return exact;
  return [...commands].sort((a, b) => distance(a.name, needle) - distance(b.name, needle)).slice(0, 6);
}

/**
 * Parse a raw composer input. Returns a non-null command spec when the input
 * starts with `/` and matches an entry in the registry. Everything else is a
 * regular chat message.
 */
export interface ParsedCommand {
  spec: CommandSpec;
  ctx: Omit<CommandCtx, 'api' | 'notify' | 'setStatus'>;
}

export function parseCommand(raw: string): ParsedCommand | null {
  if (!raw.startsWith('/')) return null;
  const trimmed = raw.slice(1).trim();
  if (!trimmed) return null;
  const [name, ...args] = trimmed.split(/\s+/);
  if (!name) return null;
  const spec = findCommand(name);
  if (!spec) return null;
  return {spec, ctx: {raw, args}};
}

/* ── default commands ──────────────────────────────────────────── */

registerCommand({
  name: 'help',
  aliases: ['?'],
  description: 'Show every command, grouped by category',
  category: 'misc',
  run({notify}) {
    useUiStore.getState().setOverlay('help');
    notify('info', 'press Esc to close');
  }
});

registerCommand({
  name: 'quit',
  aliases: ['exit', 'q'],
  description: 'Exit lhx-rag',
  category: 'misc',
  run() {
    process.exit(0);
  }
});

registerCommand({
  name: 'clear',
  description: 'Clear the transcript view (does not delete history)',
  category: 'misc',
  run() {
    useUiStore.getState().setStatus('cleared local view');
    const sid = useSessionStore.getState().activeId;
    if (sid) useChatStore.getState().clearLocal(sid);
  }
});

registerCommand({
  name: 'sessions',
  aliases: ['ls'],
  description: 'Reload the session list from the server',
  category: 'session',
  async run({api, notify}) {
    await useSessionStore.getState().refresh(api);
    notify('ok', `loaded ${useSessionStore.getState().sessions.length} sessions`);
  }
});

registerCommand({
  name: 'new',
  description: 'Create a new session and switch to it',
  category: 'session',
  async run({api, args, notify}) {
    const title = args.length > 0 ? args.join(' ') : null;
    const created = await useSessionStore.getState().create(api, title);
    if (created) {
      await useChatStore.getState().loadSession(api, created.id);
      notify('ok', 'new session');
    }
  }
});

registerCommand({
  name: 'switch',
  usage: '/switch <session-id-prefix>',
  description: 'Switch to another session by id prefix or index',
  category: 'session',
  async run({api, args, notify}) {
    const target = args[0];
    if (!target) {
      notify('warn', 'usage: /switch <id-prefix|index>');
      return;
    }
    const sessions = useSessionStore.getState().sessions;
    let match = sessions.find((s) => s.id.startsWith(target));
    if (!match) {
      const idx = Number.parseInt(target, 10);
      if (!Number.isNaN(idx) && sessions[idx]) match = sessions[idx];
    }
    if (!match) {
      notify('error', `no session matches ${target}`);
      return;
    }
    useSessionStore.getState().select(match.id);
    await useChatStore.getState().loadSession(api, match.id);
    notify('ok', `switched to ${match.title ?? match.id.slice(0, 8)}`);
  }
});

registerCommand({
  name: 'title',
  usage: '/title <new title>',
  description: 'Rename the active session',
  category: 'session',
  async run({api, raw, notify}) {
    const title = raw.replace(/^\/title\s*/, '').trim();
    if (!title) {
      notify('warn', 'usage: /title <new title>');
      return;
    }
    const sid = useSessionStore.getState().activeId;
    if (!sid) {
      notify('warn', 'no active session');
      return;
    }
    await useSessionStore.getState().rename(api, sid, title);
    notify('ok', 'renamed');
  }
});

registerCommand({
  name: 'delete',
  aliases: ['rm'],
  description: 'Delete the active session',
  category: 'session',
  async run({api, notify}) {
    const sid = useSessionStore.getState().activeId;
    if (!sid) {
      notify('warn', 'no active session');
      return;
    }
    await useSessionStore.getState().remove(api, sid);
    const next = useSessionStore.getState().activeId;
    if (next) {
      await useChatStore.getState().loadSession(api, next);
    } else {
      useChatStore.getState().reset();
    }
    notify('ok', 'session deleted');
  }
});

registerCommand({
  name: 'rag',
  usage: '/rag on|off',
  description: 'Toggle retrieval-augmented generation for this turn onward',
  category: 'rag',
  run({args, notify}) {
    const arg = args[0]?.toLowerCase();
    const current = useChatStore.getState().useRag;
    const next = arg === 'on' ? true : arg === 'off' ? false : !current;
    useChatStore.getState().setUseRag(next);
    notify('info', `rag: ${next ? 'on' : 'off'}`);
  }
});

registerCommand({
  name: 'think',
  usage: '/think on|off|low|medium|high',
  description: 'Toggle or set the reasoning depth',
  category: 'rag',
  run({args, notify}) {
    const arg = args[0]?.toLowerCase();
    const value =
      arg === 'on' || arg === 'true'
        ? true
        : arg === 'off' || arg === 'false'
          ? false
          : arg === 'low' || arg === 'medium' || arg === 'high'
            ? arg
            : undefined;
    if (value === undefined) {
      notify('warn', 'usage: /think on|off|low|medium|high');
      return;
    }
    useChatStore.getState().setThink(value);
    notify('info', `think: ${value}`);
  }
});

registerCommand({
  name: 'regenerate',
  aliases: ['retry', 'r'],
  description: 'Re-stream the last assistant reply',
  category: 'chat',
  async run({api, notify}) {
    const sid = useSessionStore.getState().activeId;
    if (!sid) {
      notify('warn', 'no active session');
      return;
    }
    if (useChatStore.getState().streaming) {
      notify('warn', 'already streaming');
      return;
    }
    await useChatStore.getState().regenerate(api, sid);
  }
});

registerCommand({
  name: 'stop',
  description: 'Cancel the streaming reply',
  category: 'chat',
  run({notify}) {
    if (!useChatStore.getState().streaming) {
      notify('info', 'nothing to stop');
      return;
    }
    useChatStore.getState().stop();
    notify('ok', 'stop requested');
  }
});

registerCommand({
  name: 'whoami',
  description: 'Show the currently logged-in user',
  category: 'auth',
  run({notify}) {
    const user = useAuthStore.getState().user;
    if (!user) notify('warn', 'not logged in');
    else notify('info', `${user.email} (${user.id.slice(0, 8)})`);
  }
});

registerCommand({
  name: 'logout',
  description: 'Forget local credentials and return to the login screen',
  category: 'auth',
  async run({api, notify}) {
    // Tear down store state in dependency order — chat depends on session,
    // session depends on auth, ui carries pane/overlay flags that should
    // not survive the trip to the login screen.
    await useAuthStore.getState().logout(api);
    useSessionStore.getState().reset();
    useChatStore.getState().reset();
    // The ui store has no formal reset() yet; nudge the bits that would
    // otherwise leak into the next session (an open overlay, a non-
    // composer pane focus, a stale "follow bottom" offset).
    const ui = useUiStore.getState();
    ui.setOverlay(null);
    ui.setPane('composer');
    ui.setFollowBottom(true);
    ui.setCommandPaletteOpen(false);
    ui.setStatus('logged out');
    // Provider cache is per-user; the next login should re-fetch from
    // scratch so we don't show another account's provider names in the
    // sidebar footer.
    useProviderStore.getState().invalidate();
    useProviderStore.setState({providers: []});
    notify('ok', 'logged out');
  }
});
