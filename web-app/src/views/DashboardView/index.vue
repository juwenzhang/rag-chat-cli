<template>
  <div :class="styles.dashboard">
    <h1 :class="styles.dashboard__title">
      {{ t('dashboard.welcome', { name: auth.user?.display_name ?? auth.user?.email ?? '…' }) }}
    </h1>

    <TokenCard />
  </div>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import { useAuthStore } from '@/stores/auth'
  import TokenCard from '@/components/TokenCard'

  const { t } = useI18n()
  const auth = useAuthStore()
</script>

<style module="styles" src="./index.module.less" lang="less"></style>
