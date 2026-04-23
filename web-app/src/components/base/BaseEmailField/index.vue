<template>
  <BaseInput
    :model-value="modelValue"
    :label="label ?? t('auth.login.email')"
    :placeholder="placeholder ?? t('auth.login.emailPlaceholder')"
    type="email"
    autocomplete="email"
    :required="required"
    :error="error"
    @update:model-value="(v: string) => $emit('update:modelValue', v)"
  />
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import BaseInput from '@/components/base/BaseInput'

  defineProps<{
    modelValue: string
    label?: string
    placeholder?: string
    required?: boolean
    error?: string
  }>()
  defineEmits<{ (e: 'update:modelValue', v: string): void }>()

  const { t } = useI18n()
</script>
