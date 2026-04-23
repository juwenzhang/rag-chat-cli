import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'
import type { ApiError } from '@/types/api'
import { readToken, writeToken, clearToken } from '@/composables/useToken'

export class AppError extends Error {
  constructor(
    public code: string,
    message: string,
    public status?: number,
    public details?: Record<string, unknown>,
    public requestId?: string,
  ) {
    super(message)
    this.name = 'AppError'
  }
}

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
}

// 基础实例
export const http: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use((config) => {
  const t = readToken()
  if (t?.accessToken) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${t.accessToken}`
  }
  return config
})

let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const t = readToken()
  if (!t?.refreshToken) throw new AppError('no_refresh_token', 'No refresh token', 401)
  const { data } = await axios.post('/api/v1/auth/refresh', {
    refresh_token: t.refreshToken,
  })
  const expiresAt = Date.now() + data.expires_in * 1000
  writeToken({ accessToken: data.access_token, refreshToken: t.refreshToken, expiresAt })
  return data.access_token
}

http.interceptors.response.use(
  (resp) => resp,
  async (err: AxiosError<ApiError>) => {
    const cfg = err.config as RetriableConfig | undefined
    const status = err.response?.status

    // 401 一次性自动刷新
    if (status === 401 && cfg && !cfg._retry && !cfg.url?.includes('/auth/')) {
      cfg._retry = true
      try {
        refreshPromise ??= refreshAccessToken().finally(() => {
          refreshPromise = null
        })
        const newToken = await refreshPromise
        cfg.headers = cfg.headers ?? {}
        cfg.headers.Authorization = `Bearer ${newToken}`
        return http(cfg)
      } catch (e) {
        clearToken()
        // 让上层路由守卫把用户踢回 /login
        window.location.href = '/login'
        throw e
      }
    }

    const payload = err.response?.data
    const code = payload?.code ?? 'network_error'
    const message = payload?.message ?? err.message ?? 'Network error'
    throw new AppError(code, message, status, payload?.details, payload?.request_id)
  },
)

// 便捷方法
export async function get<T>(url: string, cfg?: AxiosRequestConfig): Promise<T> {
  return (await http.get<T>(url, cfg)).data
}
export async function post<T>(url: string, body?: unknown, cfg?: AxiosRequestConfig): Promise<T> {
  return (await http.post<T>(url, body, cfg)).data
}
export async function del<T>(url: string, cfg?: AxiosRequestConfig): Promise<T> {
  return (await http.delete<T>(url, cfg)).data
}
