/**
 * Server-side environment variable accessor.
 *
 * Throws on missing required keys so misconfigurations fail loudly at
 * boot rather than silently in an API call.
 *
 * NEVER import this file in client components — it touches process.env
 * keys that are not prefixed with NEXT_PUBLIC_.
 */

import "server-only";

function req(key: string, fallback?: string): string {
  const v = process.env[key];
  if (v === undefined || v === "") {
    if (fallback !== undefined) return fallback;
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return v;
}

function bool(key: string, fallback: boolean): boolean {
  const v = process.env[key];
  if (v === undefined || v === "") return fallback;
  return v === "true" || v === "1";
}

export const env = {
  RAG_API_URL: req("RAG_API_URL", "http://localhost:8000"),
  SESSION_COOKIE_NAME: req("SESSION_COOKIE_NAME", "rag_session"),
  SESSION_COOKIE_DOMAIN: process.env.SESSION_COOKIE_DOMAIN || undefined,
  SESSION_COOKIE_SECURE: bool("SESSION_COOKIE_SECURE", false),
} as const;
