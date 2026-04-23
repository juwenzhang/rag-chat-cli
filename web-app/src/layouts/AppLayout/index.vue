<template>
  <div :class="styles.appLayout">
    <header :class="styles.appLayout__header">
      <div :class="styles.appLayout__brand">
        <span :class="styles.appLayout__logo" class="i-lucide-message-square-code" />
        <span :class="styles.appLayout__name">{{ t('app.brand') }}</span>
      </div>

      <nav :class="styles.appLayout__nav">
        <RouterLink
          v-for="item in nav"
          :key="item.name"
          :to="{ name: item.name }"
          :class="styles.appLayout__navItem"
          active-class="is-active"
        >
          {{ t(item.label) }}
        </RouterLink>
      </nav>

      <div :class="styles.appLayout__right">
        <ApiStatusBadge />
        <button :class="styles.appLayout__iconBtn" :title="ui.theme" @click="ui.toggle">
          <span :class="ui.theme === 'dark' ? 'i-lucide-sun' : 'i-lucide-moon'" />
        </button>
        <BaseButton variant="ghost" size="small" @click="onLogout">
          <span class="i-lucide-log-out mr-1" />
          {{ t('nav.logout') }}
        </BaseButton>
      </div>
    </header>

    <main :class="styles.appLayout__main">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
  import { useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { useAuthStore } from '@/stores/auth'
  import { useUiStore } from '@/stores/ui'
  import BaseButton from '@/components/base/BaseButton'
  import ApiStatusBadge from '@/components/ApiStatusBadge'

  const { t } = useI18n()
  const router = useRouter()
  const auth = useAuthStore()
  const ui = useUiStore()

  const nav = [
    { name: 'dashboard', label: 'nav.dashboard' },
    { name: 'token', label: 'nav.token' },
    { name: 'profile', label: 'nav.profile' },
  ]

  if (auth.isAuthed && !auth.user) {
    auth.fetchMe().catch(() => void 0)
  }

  async function onLogout(): Promise<void> {
    await auth.logout()
    router.replace({ name: 'login' })
  }
</script>

<style module="styles" src="./index.module.less" lang="less"></style>
