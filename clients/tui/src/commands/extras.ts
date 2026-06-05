/**
 * Tier-A command implementations: knowledge base, providers / models,
 * preferences, message edit / delete / evaluate. These complement the core
 * commands in ``registry.ts``.
 *
 * Why split: the core registry stays focused on session / chat / auth, while
 * these commands are largely "admin" actions that talk to non-chat endpoints.
 * Keeping them separate also makes the file diff easier to review.
 */
import {MessageRole} from '../api/enums';
import {ApiError} from '../api/types';
import {useChatStore} from '../store/chat-store';
import {useProviderStore} from '../store/provider-store';
import {useSessionStore} from '../store/session-store';
import {useUiStore} from '../store/ui-store';
import {registerCommand} from './registry';
import type {CommandCtx} from './types';

/** Invalidate the provider cache; used after every mutating providers call. */
function invalidateProviders(): void {
  useProviderStore.getState().invalidate();
}

/* ── helpers ───────────────────────────────────────────────────────── */

function fmtError(err: unknown): string {
  if (err instanceof ApiError) return `${err.code}: ${err.message}`;
  if (err instanceof Error) return err.message;
  return 'unknown error';
}

function bytesToHuman(bytes?: number | null): string {
  if (bytes == null) return '?';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)}${units[i]}`;
}

function pickProvider(args: string[], list: {id: string; name: string}[]):
  | {id: string; name: string}
  | null {
  const target = args[0];
  if (!target) return null;
  const byPrefix = list.find((p) => p.id.startsWith(target));
  if (byPrefix) return byPrefix;
  const byName = list.find((p) => p.name.toLowerCase() === target.toLowerCase());
  if (byName) return byName;
  const idx = Number.parseInt(target, 10);
  if (!Number.isNaN(idx) && list[idx]) return list[idx];
  return null;
}

/* ── /pref ─────────────────────────────────────────────────────────── */

registerCommand({
  name: 'pref',
  aliases: ['preferences'],
  usage: '/pref [show|set <key> <value>|clear <key>]',
  description: 'Inspect or change per-user defaults (provider, model, embed, rag)',
  category: 'config',
  async run(ctx: CommandCtx) {
    const sub = ctx.args[0]?.toLowerCase() ?? 'show';
    try {
      if (sub === 'show' || sub === 'get') {
        const pref = await ctx.api.getPreferences();
        ctx.notify(
          'info',
          `provider=${pref.default_provider_id?.slice(0, 8) ?? '∅'} ` +
            `model=${pref.default_model ?? '∅'} ` +
            `embed=${pref.default_embedding_model ?? '∅'} ` +
            `rag=${pref.default_use_rag ? 'on' : 'off'}`
        );
        return;
      }
      if (sub === 'set') {
        const key = ctx.args[1]?.toLowerCase();
        const raw = ctx.args.slice(2).join(' ').trim();
        if (!key || !raw) {
          ctx.notify('warn', 'usage: /pref set <provider|model|embed|rag> <value>');
          return;
        }
        const body: Record<string, unknown> = {};
        if (key === 'provider') body['default_provider_id'] = raw;
        else if (key === 'model') body['default_model'] = raw;
        else if (key === 'embed' || key === 'embedding') body['default_embedding_model'] = raw;
        else if (key === 'rag') body['default_use_rag'] = raw === 'on' || raw === 'true';
        else {
          ctx.notify('warn', `unknown key: ${key}`);
          return;
        }
        await ctx.api.putPreferences(body);
        ctx.notify('ok', `pref ${key} updated`);
        return;
      }
      if (sub === 'clear') {
        const key = ctx.args[1]?.toLowerCase();
        const body: Record<string, unknown> = {};
        if (key === 'provider') body['clear_default_provider'] = true;
        else if (key === 'model') body['clear_default_model'] = true;
        else if (key === 'embed' || key === 'embedding') body['clear_default_embedding_model'] = true;
        else {
          ctx.notify('warn', 'usage: /pref clear <provider|model|embed>');
          return;
        }
        await ctx.api.putPreferences(body);
        ctx.notify('ok', `pref ${key} cleared`);
        return;
      }
      ctx.notify('warn', 'usage: /pref [show|set|clear]');
    } catch (err) {
      ctx.notify('error', fmtError(err));
    }
  }
});

/* ── /kb ───────────────────────────────────────────────────────────── */

registerCommand({
  name: 'kb',
  aliases: ['knowledge'],
  usage: '/kb [list|add <title>|rm <id>|reindex|search <query>]',
  description: 'Manage the knowledge base (list / add / remove / reindex / search)',
  category: 'knowledge',
  async run(ctx: CommandCtx) {
    const sub = ctx.args[0]?.toLowerCase() ?? 'list';
    try {
      if (sub === 'list' || sub === 'ls') {
        const page = await ctx.api.listDocuments(1, 50);
        if (page.items.length === 0) {
          ctx.notify('info', 'no documents');
          return;
        }
        for (const [i, doc] of page.items.entries()) {
          ctx.notify(
            'info',
            `[${i}] ${doc.id.slice(0, 8)} — ${doc.title} · ${doc.source}`
          );
        }
        return;
      }
      if (sub === 'add') {
        const title = ctx.args.slice(1).join(' ').trim();
        if (!title) {
          ctx.notify('warn', 'usage: /kb add <title>');
          return;
        }
        // Body is a placeholder — full document upload (multi-line / file path)
        // is out of scope for the slash-command surface; users with large docs
        // should use the website. We still accept a 1-line "add" so the CLI
        // can stash quick notes.
        const created = await ctx.api.createDocument({
          title,
          source: 'cli-quick-note',
          body: `# ${title}\n\n_(empty — edit via the web UI to add body content)_\n`
        });
        ctx.notify('ok', `created ${created.id.slice(0, 8)}`);
        return;
      }
      if (sub === 'rm' || sub === 'delete') {
        const target = ctx.args[1];
        if (!target) {
          ctx.notify('warn', 'usage: /kb rm <id-prefix>');
          return;
        }
        const page = await ctx.api.listDocuments(1, 200);
        const match = page.items.find((d) => d.id.startsWith(target));
        if (!match) {
          ctx.notify('error', `no document matches ${target}`);
          return;
        }
        await ctx.api.deleteDocument(match.id);
        ctx.notify('ok', `deleted ${match.title}`);
        return;
      }
      if (sub === 'reindex') {
        await ctx.api.reindexDocuments();
        ctx.notify('ok', 'reindex queued');
        return;
      }
      if (sub === 'search' || sub === 'q') {
        const q = ctx.args.slice(1).join(' ').trim();
        if (!q) {
          ctx.notify('warn', 'usage: /kb search <query>');
          return;
        }
        const hits = await ctx.api.searchKnowledge(q, 5);
        if (hits.length === 0) {
          ctx.notify('info', 'no hits');
          return;
        }
        for (const [i, hit] of hits.entries()) {
          const snippet = hit.snippet.replace(/\s+/g, ' ').slice(0, 80);
          ctx.notify(
            'info',
            `[${i}] ${hit.score.toFixed(3)} · ${hit.title ?? '(untitled)'} — ${snippet}`
          );
        }
        return;
      }
      ctx.notify('warn', 'usage: /kb [list|add|rm|reindex|search]');
    } catch (err) {
      ctx.notify('error', fmtError(err));
    }
  }
});

/* ── /providers ───────────────────────────────────────────────────── */

registerCommand({
  name: 'providers',
  aliases: ['provider'],
  usage: '/providers [list|add <name> <type> <base_url> [api_key]|rm <id>|test <type> <url> [key]|default <id>]',
  description: 'Manage LLM providers (list / add / remove / test / set default)',
  category: 'config',
  async run(ctx: CommandCtx) {
    const sub = ctx.args[0]?.toLowerCase() ?? 'list';
    try {
      if (sub === 'list' || sub === 'ls') {
        const list = await ctx.api.listProviders();
        if (list.length === 0) {
          ctx.notify('info', 'no providers configured');
          return;
        }
        for (const [i, p] of list.entries()) {
          const tag = `${p.is_default ? '★' : ' '}${p.enabled ? '' : ' (disabled)'}`;
          ctx.notify(
            'info',
            `[${i}] ${tag} ${p.id.slice(0, 8)} — ${p.name} · ${p.type} · ${p.base_url}` +
              (p.has_api_key ? ' · key✓' : '')
          );
        }
        return;
      }
      if (sub === 'add') {
        const [, name, typeArg, baseUrl, apiKey] = ctx.args;
        if (!name || !typeArg || !baseUrl) {
          ctx.notify('warn', 'usage: /providers add <name> <ollama|openai> <base_url> [api_key]');
          return;
        }
        if (typeArg !== 'ollama' && typeArg !== 'openai') {
          ctx.notify('warn', `type must be ollama|openai (got ${typeArg})`);
          return;
        }
        const created = await ctx.api.createProvider({
          name,
          type: typeArg,
          base_url: baseUrl,
          api_key: apiKey ?? null,
          test_connectivity: true
        });
        invalidateProviders();
        ctx.notify('ok', `provider ${created.name} created (${created.id.slice(0, 8)})`);
        return;
      }
      if (sub === 'rm' || sub === 'delete') {
        const list = await ctx.api.listProviders();
        const match = pickProvider(ctx.args.slice(1), list);
        if (!match) {
          ctx.notify('warn', 'usage: /providers rm <id-prefix|name|index>');
          return;
        }
        await ctx.api.deleteProvider(match.id);
        invalidateProviders();
        ctx.notify('ok', `deleted ${match.name}`);
        return;
      }
      if (sub === 'default') {
        const list = await ctx.api.listProviders();
        const match = pickProvider(ctx.args.slice(1), list);
        if (!match) {
          ctx.notify('warn', 'usage: /providers default <id-prefix|name|index>');
          return;
        }
        await ctx.api.updateProvider(match.id, {is_default: true});
        invalidateProviders();
        ctx.notify('ok', `default → ${match.name}`);
        return;
      }
      if (sub === 'test') {
        const [, typeArg, baseUrl, apiKey] = ctx.args;
        if (!typeArg || !baseUrl) {
          ctx.notify('warn', 'usage: /providers test <ollama|openai> <base_url> [api_key]');
          return;
        }
        if (typeArg !== 'ollama' && typeArg !== 'openai') {
          ctx.notify('warn', `type must be ollama|openai (got ${typeArg})`);
          return;
        }
        const result = await ctx.api.testProvider({
          type: typeArg,
          base_url: baseUrl,
          api_key: apiKey ?? null
        });
        ctx.notify(result.ok ? 'ok' : 'error', result.detail);
        return;
      }
      ctx.notify('warn', 'usage: /providers [list|add|rm|default|test]');
    } catch (err) {
      ctx.notify('error', fmtError(err));
    }
  }
});

/* ── /models ──────────────────────────────────────────────────────── */

registerCommand({
  name: 'models',
  usage: '/models [list [provider]|pull <provider> <model>|rm <provider> <model>]',
  description: 'List, pull or delete models on a provider',
  category: 'config',
  async run(ctx: CommandCtx) {
    const sub = ctx.args[0]?.toLowerCase() ?? 'list';
    try {
      const providers = await ctx.api.listProviders();
      const resolveProvider = (token?: string) => {
        if (!token) {
          return providers.find((p) => p.is_default) ?? providers[0] ?? null;
        }
        return pickProvider([token], providers);
      };

      if (sub === 'list' || sub === 'ls') {
        const provider = resolveProvider(ctx.args[1]);
        if (!provider) {
          ctx.notify('warn', 'no provider — /providers add ... first');
          return;
        }
        const models = await ctx.api.listProviderModels(provider.id);
        if (models.length === 0) {
          ctx.notify('info', `${provider.name}: no models`);
          return;
        }
        for (const [i, m] of models.entries()) {
          const desc = m.description ? ` · ${m.description}` : '';
          ctx.notify(
            'info',
            `[${i}] ${m.id} · ${m.kind ?? 'chat'} · ${bytesToHuman(m.size)}${desc}`
          );
        }
        return;
      }
      if (sub === 'pull') {
        const provider = resolveProvider(ctx.args[1]);
        const model = ctx.args[2];
        if (!provider || !model) {
          ctx.notify('warn', 'usage: /models pull <provider> <model>');
          return;
        }
        ctx.notify('info', `pulling ${model} on ${provider.name}...`);
        const response = await ctx.api.openModelPullStream(provider.id, model);
        // Drain SSE — surface the last status only to keep the toast stack
        // tame; full progress lives in the website.
        const text = await response.text();
        const lastStatus = text.match(/"status":\s*"([^"]+)"/g)?.pop();
        ctx.notify('ok', `pull finished${lastStatus ? ' — ' + lastStatus : ''}`);
        return;
      }
      if (sub === 'rm' || sub === 'delete') {
        const provider = resolveProvider(ctx.args[1]);
        const model = ctx.args[2];
        if (!provider || !model) {
          ctx.notify('warn', 'usage: /models rm <provider> <model>');
          return;
        }
        await ctx.api.deleteProviderModel(provider.id, model);
        ctx.notify('ok', `removed ${model} from ${provider.name}`);
        return;
      }
      ctx.notify('warn', 'usage: /models [list|pull|rm]');
    } catch (err) {
      ctx.notify('error', fmtError(err));
    }
  }
});

/* ── /model — change the active session's model pin ──────────────── */

/**
 * Pick the "best" provider for a model switch when the user didn't say
 * which one. Order:
 *
 * 1. The provider currently pinned on the active session (preserve the
 *    user's existing routing).
 * 2. The user's default provider (the ★ row in ``/providers list``).
 * 3. Whatever ``/providers`` returned first.
 */
function pickActiveProvider(
  providers: {id: string; name: string; is_default: boolean}[],
  sessionProviderId: string | null | undefined
): {id: string; name: string} | null {
  if (sessionProviderId) {
    const pinned = providers.find((p) => p.id === sessionProviderId);
    if (pinned) return pinned;
  }
  return providers.find((p) => p.is_default) ?? providers[0] ?? null;
}

registerCommand({
  name: 'model',
  aliases: ['m'],
  usage: '/model [show|<model>|set [provider] <model>|clear]',
  description:
    "Inspect or change the active session's model. Shorthand: /model qwen3-coder-next:cloud",
  category: 'config',
  async run(ctx: CommandCtx) {
    const sid = useSessionStore.getState().activeId;
    if (!sid) {
      ctx.notify('warn', 'no active session');
      return;
    }
    const sub = ctx.args[0]?.toLowerCase();
    try {
      // /model            → show
      // /model show       → show
      if (sub === undefined || sub === 'show' || sub === 'get') {
        const session = useSessionStore
          .getState()
          .sessions.find((s) => s.id === sid);
        const providers = await ctx.api.listProviders();
        const provider = providers.find((p) => p.id === session?.provider_id);
        ctx.notify(
          'info',
          `provider=${provider?.name ?? '∅ (use /pref default)'} · ` +
            `model=${session?.model ?? '∅ (fallback to env / /pref)'}`
        );
        // Show top 5 available model ids on the resolved provider so the
        // user knows what to type next, without leaving the chat view.
        const target = pickActiveProvider(providers, session?.provider_id);
        if (target) {
          try {
            const models = await ctx.api.listProviderModels(target.id);
            const preview = models
              .filter((m) => (m.kind ?? 'chat') === 'chat')
              .slice(0, 5)
              .map((m) => m.id)
              .join(', ');
            if (preview) {
              ctx.notify('info', `available on ${target.name}: ${preview}`);
            }
          } catch {
            /* upstream offline — ignore */
          }
        }
        return;
      }
      // /model clear      → drop the pin entirely
      if (sub === 'clear' || sub === 'reset') {
        const updated = await ctx.api.updateSession(sid, {
          clear_model: true,
          clear_provider_id: true
        });
        useSessionStore.getState().upsertLocal(updated);
        ctx.notify('ok', 'session pin cleared — using /pref defaults');
        return;
      }
      // /model set [provider] <model>
      // /model <model>      → shorthand; reuse current/default provider
      const providers = await ctx.api.listProviders();
      let providerToken: string | undefined;
      let modelTag: string | undefined;
      if (sub === 'set') {
        // Two-arg form: provider + model. One-arg form: model only.
        if (ctx.args.length >= 3) {
          providerToken = ctx.args[1];
          modelTag = ctx.args.slice(2).join(' ');
        } else {
          modelTag = ctx.args[1];
        }
      } else {
        // Whole input is the model tag, e.g. "/model qwen3-coder-next:cloud".
        // Joining preserves any spaces (rare, but harmless).
        modelTag = ctx.args.join(' ');
      }
      modelTag = modelTag?.trim();
      if (!modelTag) {
        ctx.notify(
          'warn',
          'usage: /model <model> · /model set <provider> <model> · /model clear · /model show'
        );
        return;
      }
      const session = useSessionStore.getState().sessions.find((s) => s.id === sid);
      const provider = providerToken
        ? pickProvider([providerToken], providers)
        : pickActiveProvider(providers, session?.provider_id);
      if (!provider) {
        ctx.notify(
          'error',
          providerToken
            ? `no provider matches ${providerToken}`
            : 'no provider configured — /providers add ... first'
        );
        return;
      }
      const updated = await ctx.api.updateSession(sid, {
        provider_id: provider.id,
        model: modelTag
      });
      useSessionStore.getState().upsertLocal(updated);
      ctx.notify('ok', `pinned ${provider.name} · ${modelTag}`);
    } catch (err) {
      ctx.notify('error', fmtError(err));
    }
  }
});

/* ── /register (fallback for already-logged-in flow) ──────────────── */

registerCommand({
  name: 'register',
  usage: '/register <email> <password> [display name]',
  description: 'Create an account from the command line (also available on the login screen)',
  category: 'auth',
  async run(ctx: CommandCtx) {
    const [emailArg, password, ...rest] = ctx.args;
    if (!emailArg || !password) {
      ctx.notify('warn', 'usage: /register <email> <password> [display name]');
      return;
    }
    const displayName = rest.join(' ').trim() || undefined;
    try {
      const user = await ctx.api.register(emailArg, password, displayName);
      ctx.notify('ok', `created ${user.email}`);
    } catch (err) {
      ctx.notify('error', fmtError(err));
    }
  }
});

/* ── /edit /rm-msg /eval ──────────────────────────────────────────── */

function lastAssistantId(): string | null {
  const messages = useChatStore.getState().messages;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (m && m.role === MessageRole.Assistant && !m.id.startsWith('temp-')) return m.id;
  }
  return null;
}

function lastUserId(): string | null {
  const messages = useChatStore.getState().messages;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (m && m.role === MessageRole.User && !m.id.startsWith('temp-')) return m.id;
  }
  return null;
}

registerCommand({
  name: 'edit',
  usage: '/edit <new content>',
  description: 'Edit your last user message in the active session',
  category: 'chat',
  async run(ctx: CommandCtx) {
    const content = ctx.args.join(' ').trim();
    if (!content) {
      ctx.notify('warn', 'usage: /edit <new content>');
      return;
    }
    const sid = useSessionStore.getState().activeId;
    if (!sid) {
      ctx.notify('warn', 'no active session');
      return;
    }
    const target = lastUserId();
    if (!target) {
      ctx.notify('warn', 'no editable message');
      return;
    }
    try {
      await ctx.api.editMessage(target, content);
      await useChatStore.getState().loadSession(ctx.api, sid);
      ctx.notify('ok', 'message edited');
    } catch (err) {
      ctx.notify('error', fmtError(err));
    }
  }
});

registerCommand({
  name: 'rmsg',
  aliases: ['delmsg'],
  description: 'Delete the last assistant message in the active session',
  category: 'chat',
  async run(ctx: CommandCtx) {
    const sid = useSessionStore.getState().activeId;
    if (!sid) {
      ctx.notify('warn', 'no active session');
      return;
    }
    const target = lastAssistantId();
    if (!target) {
      ctx.notify('warn', 'no deletable message');
      return;
    }
    try {
      await ctx.api.deleteMessage(target);
      await useChatStore.getState().loadSession(ctx.api, sid);
      ctx.notify('ok', 'message deleted');
    } catch (err) {
      ctx.notify('error', fmtError(err));
    }
  }
});

registerCommand({
  name: 'eval',
  aliases: ['evaluate'],
  description: 'Run the resident judge against the last assistant message',
  category: 'chat',
  async run(ctx: CommandCtx) {
    const target = lastAssistantId();
    if (!target) {
      ctx.notify('warn', 'no assistant message to evaluate');
      return;
    }
    try {
      const result = await ctx.api.evaluateMessage(target);
      useUiStore.getState().setStatus(
        `eval overall=${result.overall} risk=${result.risk}`
      );
      ctx.notify(
        'ok',
        `overall=${result.overall} help=${result.helpfulness} ground=${result.groundedness} cite=${result.citation_quality} comp=${result.completeness} risk=${result.risk}`
      );
    } catch (err) {
      ctx.notify('error', fmtError(err));
    }
  }
});
