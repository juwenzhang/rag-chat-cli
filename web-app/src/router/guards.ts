import type { Router } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

export function installGuards(router: Router): void {
  router.beforeEach((to) => {
    const auth = useAuthStore()
    if (to.meta.public) return true
    if (!auth.isAuthed) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
    return true
  })
}
