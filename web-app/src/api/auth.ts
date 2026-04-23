import { post, get } from './http'
import type { LoginRequest, LoginResponse, User } from '@/types/api'

export const authApi = {
  login: (body: LoginRequest) => post<LoginResponse>('/v1/auth/login', body),
  me: () => get<User>('/v1/auth/me'),
  logout: () => post<void>('/v1/auth/logout'),
}
