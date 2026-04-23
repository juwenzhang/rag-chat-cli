<template>
  <BaseInput
    :model-value="modelValue"
    :label="label ?? t('auth.login.password')"
    :placeholder="placeholder ?? t('auth.login.passwordPlaceholder')"
    type="password"
    autocomplete="current-password"
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
