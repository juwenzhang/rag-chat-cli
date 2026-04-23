<template>
  <div :class="styles.baseInput">
    <label v-if="label" :class="styles.baseInput__label" :for="inputId">
      {{ label }}
      <span v-if="required" :class="styles.baseInput__required">*</span>
    </label>

    <ElInput
      :id="inputId"
      :class="styles.baseInput__control"
      :model-value="modelValue"
      :type="type"
      :placeholder="placeholder"
      :disabled="disabled"
      :autocomplete="autocomplete"
      :show-password="type === 'password'"
      @update:model-value="onUpdate"
    />

    <p v-if="error" :class="styles.baseInput__error">{{ error }}</p>
    <p v-else-if="hint" :class="styles.baseInput__hint">{{ hint }}</p>
  </div>
</template>

<script setup lang="ts">
  import { computed, useId } from 'vue'
  import { ElInput } from 'element-plus'

  withDefaults(
    defineProps<{
      modelValue: string
      label?: string
      placeholder?: string
      type?: 'text' | 'password' | 'email'
      required?: boolean
      disabled?: boolean
      error?: string
      hint?: string
      autocomplete?: string
    }>(),
    { type: 'text', required: false, disabled: false },
  )

  const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

  const _id = useId()
  const inputId = computed(() => `base-input-${_id}`)

  function onUpdate(v: string | number): void {
    emit('update:modelValue', String(v))
  }
</script>

<style module="styles" src="./index.module.less" lang="less"></style>
