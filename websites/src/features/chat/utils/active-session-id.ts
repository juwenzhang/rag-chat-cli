/**
 * Extract the active chat session id from a Next.js pathname.
 *
 * The chat URL space uses ``/chat/<sessionId>``; ``/chat`` itself
 * is the empty state and yields ``null``.
 */
export function activeSessionId(pathname: string): string | null {
  const match = pathname.match(/^\/chat\/([^/]+)/);
  return match ? match[1] : null;
}
