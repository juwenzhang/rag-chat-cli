import type {ApiClient} from '../api/client';

export interface CommandCtx {
  api: ApiClient;
  args: string[];
  raw: string;
  notify: (level: 'info' | 'warn' | 'error' | 'ok', message: string) => void;
  setStatus: (status: string) => void;
}

export interface CommandSpec {
  name: string;
  aliases?: string[];
  description: string;
  usage?: string;
  category: 'session' | 'chat' | 'rag' | 'auth' | 'config' | 'knowledge' | 'misc';
  run: (ctx: CommandCtx) => Promise<void> | void;
}
