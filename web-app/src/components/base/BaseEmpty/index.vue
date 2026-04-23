<template>
  <div :class="styles.baseEmpty">
    <span :class="styles.baseEmpty__icon" class="i-lucide-inbox" />
    <p :class="styles.baseEmpty__text">{{ text ?? t('common.empty') }}</p>
  </div>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'

  defineProps<{ text?: string }>()
  const { t } = useI18n()
</script>

<style module="styles" src="./index.module.less" lang="less"></style>
