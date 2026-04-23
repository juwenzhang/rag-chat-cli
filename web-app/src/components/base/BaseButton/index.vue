<template>
  <ElButton
    :class="[styles.baseButton, styles[`baseButton--${variant}`]]"
    :type="elType"
    :loading="loading"
    :disabled="disabled"
    :native-type="nativeType"
    :size="size"
    @click="onClick"
  >
    <slot />
  </ElButton>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { ElButton } from 'element-plus'

  type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

  const props = withDefaults(
    defineProps<{
      variant?: Variant
      loading?: boolean
      disabled?: boolean
      nativeType?: 'button' | 'submit' | 'reset'
      size?: 'small' | 'default' | 'large'
    }>(),
    { variant: 'primary', loading: false, disabled: false, nativeType: 'button', size: 'default' },
  )

  const emit = defineEmits<{ (e: 'click', ev: MouseEvent): void }>()

  const elType = computed(() => {
    switch (props.variant) {
      case 'primary':
        return 'primary'
      case 'danger':
        return 'danger'
      case 'secondary':
      case 'ghost':
      default:
        return 'default'
    }
  })

  function onClick(ev: MouseEvent): void {
    emit('click', ev)
  }
</script>

<style module="styles" src="./index.module.less" lang="less"></style>
