<template>
  <div :class="[styles.apiStatus, styles[`apiStatus--${status}`]]">
    <span :class="styles.apiStatus__dot" />
    <span :class="styles.apiStatus__text">
      {{ status === 'ok' ? t('status.apiHealthy') : t('status.apiDown') }}
    </span>
  </div>
</template>

<script setup lang="ts">
  import { onMounted, onUnmounted, ref } from 'vue'
  import { useI18n } from 'vue-i18n'

  const { t } = useI18n()
  const status = ref<'ok' | 'down' | 'pending'>('pending')
  let timer: number | null = null

  async function probe(): Promise<void> {
    try {
      const r = await fetch('/readyz')
      status.value = r.ok ? 'ok' : 'down'
    } catch {
      status.value = 'down'
    }
  }

  onMounted(() => {
    probe()
    timer = window.setInterval(probe, 15_000)
  })
  onUnmounted(() => {
    if (timer) window.clearInterval(timer)
  })
</script>

<style module="styles" src="./index.module.less" lang="less"></style>
