import { http, HttpResponse, delay } from 'msw'
import type { LoginRequest, LoginResponse, User, RefreshRequest } from '@/types/api'

// 仅用于前端独立演示；真实后端上线后把 VITE_USE_MOCK=false 即可。
const DEMO_USER: User = {
  id: 1,
  email: 'demo@rag-chat.local',
  display_name: 'Demo User',
  is_active: true,
  scope: ['user'],
  created_at: new Date().toISOString(),
}

function makeToken(kind: 'access' | 'refresh'): string {
  return `mock.${kind}.${Math.random().toString(36).slice(2)}.${Date.now()}`
}

export const handlers = [
  http.post('/api/v1/auth/login', async ({ request }) => {
    await delay(400)
    const body = (await request.json()) as LoginRequest
    if (body.email === 'demo@rag-chat.local' && body.password === 'demo1234') {
      const resp: LoginResponse = {
        access_token: makeToken('access'),
        refresh_token: makeToken('refresh'),
        expires_in: 900, // 15 min
        token_type: 'Bearer',
      }
      return HttpResponse.json(resp)
    }
    return HttpResponse.json(
      { code: 'invalid_credentials', message: 'Invalid email or password' },
      { status: 401 },
    )
  }),

  http.post('/api/v1/auth/refresh', async ({ request }) => {
    await delay(200)
    const body = (await request.json()) as RefreshRequest
    if (!body.refresh_token) {
      return HttpResponse.json({ code: 'invalid_token', message: 'No refresh token' }, { status: 401 })
    }
    return HttpResponse.json({
      access_token: makeToken('access'),
      expires_in: 900,
      token_type: 'Bearer',
    })
  }),

  http.get('/api/v1/auth/me', async ({ request }) => {
    const authz = request.headers.get('Authorization')
    if (!authz?.startsWith('Bearer ')) {
      return HttpResponse.json({ code: 'unauthorized', message: 'Missing token' }, { status: 401 })
    }
    return HttpResponse.json(DEMO_USER)
  }),

  http.post('/api/v1/auth/logout', async () => {
    await delay(120)
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/readyz', () =>
    HttpResponse.json({ ok: true, db: 'mock', redis: 'mock', ollama: 'mock' }),
  ),
]
