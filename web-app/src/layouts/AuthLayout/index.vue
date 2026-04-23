<template>
  <main :class="styles.authLayout" class="flex items-center justify-center min-h-screen">
    <div :class="styles.authLayout__brand">
      <span :class="styles.authLayout__logo" class="i-lucide-message-square-code" />
      <span :class="styles.authLayout__name">{{ t('app.brand') }}</span>
    </div>

    <div :class="styles.authLayout__slot">
      <RouterView />
    </div>

    <footer :class="styles.authLayout__footer">
      <span>rag-chat identity portal</span>
    </footer>
  </main>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'

  const { t } = useI18n()
</script>

<style module="styles" src="./index.module.less" lang="less"></style>
