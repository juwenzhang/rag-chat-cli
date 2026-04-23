<template>
  <BaseCard :title="t('dashboard.tokenCardTitle')" :subtitle="expiresHint">
    <div :class="styles.tokenCard">
      <pre :class="styles.tokenCard__value">{{ displayToken }}</pre>

      <div :class="styles.tokenCard__actions">
        <BaseButton variant="secondary" size="small" @click="onCopy">
          <span :class="[copied ? 'i-lucide-check' : 'i-lucide-copy', 'mr-1']" />
          {{ copied ? t('dashboard.copied') : t('dashboard.copy') }}
        </BaseButton>
      </div>
    </div>

    <div :class="styles.tokenCard__cli">
      <p :class="styles.tokenCard__cliHint">{{ t('dashboard.cliUsage') }}</p>
      <pre :class="styles.tokenCard__cliCode">{{ cliCmd }}</pre>
      <p :class="styles.tokenCard__cliFoot">{{ t('dashboard.cliHint') }}</p>
    </div>
  </BaseCard>
</template>

<script setup lang="ts">
  import { computed, ref } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { useAuthStore } from '@/stores/auth'
  import BaseCard from '@/components/base/BaseCard'
  import BaseButton from '@/components/base/BaseButton'

  const { t } = useI18n()
  const auth = useAuthStore()
  const copied = ref(false)

  const displayToken = computed(() => {
    const tok = auth.accessToken
    if (!tok) return '-'
    return tok.length > 64 ? `${tok.slice(0, 32)}…${tok.slice(-16)}` : tok
  })

  const expiresHint = computed(() => {
    const ms = auth.expiresAt - Date.now()
    if (ms <= 0) return 'expired'
    const min = Math.max(1, Math.floor(ms / 60000))
    return t('dashboard.tokenCardHint', { expiresIn: `${min}m` })
  })

  const cliCmd = computed(() => `rag-chat auth set-token "${auth.accessToken}"`)

  async function onCopy(): Promise<void> {
    await navigator.clipboard.writeText(auth.accessToken)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  }
</script>

<style module="styles" src="./index.module.less" lang="less"></style>
