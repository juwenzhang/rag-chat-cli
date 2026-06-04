import {existsSync, readFileSync, writeFileSync, chmodSync, unlinkSync} from 'node:fs';

import {tokenPath} from '../config/paths';
import type {TokenPair} from './types';

/**
 * Persisted token bundle. We keep both halves of the pair so the API client
 * can transparently refresh a stale access token without bouncing the user
 * back to the login screen.
 */
export interface StoredTokens {
  access_token: string;
  refresh_token: string;
  access_expires_at: string;
  refresh_expires_at: string;
  email?: string | null;
}

const FILE_MODE = 0o600;

export function loadTokens(): StoredTokens | null {
  const path = tokenPath();
  if (!existsSync(path)) return null;
  try {
    const raw = readFileSync(path, 'utf-8');
    const parsed = JSON.parse(raw) as StoredTokens;
    if (!parsed.access_token || !parsed.refresh_token) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveTokens(tokens: TokenPair, email: string | null = null): StoredTokens {
  const stored: StoredTokens = {
    access_token: tokens.access_token,
    refresh_token: tokens.refresh_token,
    access_expires_at: tokens.access_expires_at,
    refresh_expires_at: tokens.refresh_expires_at,
    email
  };
  const path = tokenPath();
  writeFileSync(path, JSON.stringify(stored, null, 2), 'utf-8');
  try {
    chmodSync(path, FILE_MODE);
  } catch {
    // best effort — Windows / certain shells reject chmod
  }
  return stored;
}

export function clearTokens(): void {
  const path = tokenPath();
  if (existsSync(path)) {
    try {
      unlinkSync(path);
    } catch {
      // ignore
    }
  }
}
