import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import { readToken, writeToken, clearToken } from '@/composables/useToken'
import type { LoginRequest, User } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const accessToken = ref<string>('')
  const refreshToken = ref<string>('')
  const expiresAt = ref<number>(0)

  const isAuthed = computed(() => !!accessToken.value && Date.now() < expiresAt.value)

  function restore(): void {
    const t = readToken()
    if (!t) return
    accessToken.value = t.accessToken
    refreshToken.value = t.refreshToken
    expiresAt.value = t.expiresAt
  }

  async function login(payload: LoginRequest): Promise<void> {
    const resp = await authApi.login(payload)
    accessToken.value = resp.access_token
    refreshToken.value = resp.refresh_token
    expiresAt.value = Date.now() + resp.expires_in * 1000
    writeToken({
      accessToken: resp.access_token,
      refreshToken: resp.refresh_token,
      expiresAt: expiresAt.value,
    })
    await fetchMe()
  }

  async function fetchMe(): Promise<void> {
    user.value = await authApi.me()
  }

  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } catch {
      // 忽略后端错误，强制清本地
    }
    user.value = null
    accessToken.value = ''
    refreshToken.value = ''
    expiresAt.value = 0
    clearToken()
  }

  return { user, accessToken, refreshToken, expiresAt, isAuthed, restore, login, fetchMe, logout }
})
