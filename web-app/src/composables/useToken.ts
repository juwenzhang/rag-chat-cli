// 仅负责 token 的读写 —— 状态管理放在 stores/auth.ts
const ACCESS_KEY = 'rag_chat_access'
const REFRESH_KEY = 'rag_chat_refresh'
const EXPIRES_KEY = 'rag_chat_expires_at'

export interface StoredToken {
  accessToken: string
  refreshToken: string
  expiresAt: number // epoch ms
}

export function readToken(): StoredToken | null {
  const a = localStorage.getItem(ACCESS_KEY)
  const r = localStorage.getItem(REFRESH_KEY)
  const e = localStorage.getItem(EXPIRES_KEY)
  if (!a || !r || !e) return null
  return { accessToken: a, refreshToken: r, expiresAt: Number(e) }
}

export function writeToken(t: StoredToken): void {
  localStorage.setItem(ACCESS_KEY, t.accessToken)
  localStorage.setItem(REFRESH_KEY, t.refreshToken)
  localStorage.setItem(EXPIRES_KEY, String(t.expiresAt))
}

export function clearToken(): void {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(EXPIRES_KEY)
}
