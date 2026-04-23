// 与 AGENTS.md §5 / §6 保持一致。后端合约变化时，此文件是唯一改动点。

export interface ApiError {
  code: string
  message: string
  request_id?: string
  details?: Record<string, unknown>
}

export interface LoginRequest {
  email: string
  password: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  expires_in: number // 秒
  token_type: 'Bearer'
}

export interface RefreshRequest {
  refresh_token: string
}

export interface RefreshResponse {
  access_token: string
  expires_in: number
  token_type: 'Bearer'
}

export interface User {
  id: number
  email: string
  display_name: string | null
  is_active: boolean
  scope: string[]
  created_at: string
}
