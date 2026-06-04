import {existsSync, mkdirSync} from 'node:fs';
import {homedir} from 'node:os';
import {join} from 'node:path';

/**
 * lhx-rag persists everything user-scoped under ~/.config/lhx-rag/. Honor
 * $XDG_CONFIG_HOME first so containerised setups keep the data on a writable
 * volume.
 */
export function configDir(): string {
  const xdg = process.env['XDG_CONFIG_HOME'];
  const root = xdg && xdg.length > 0 ? xdg : join(homedir(), '.config');
  const dir = join(root, 'lhx-rag');
  if (!existsSync(dir)) {
    mkdirSync(dir, {recursive: true});
  }
  return dir;
}

export function tokenPath(): string {
  return join(configDir(), 'token.json');
}

export function clientConfigPath(): string {
  return join(configDir(), 'client.json');
}

export function historyPath(): string {
  return join(configDir(), 'history.log');
}

export function debugLogPath(): string {
  return join(configDir(), 'debug.log');
}
