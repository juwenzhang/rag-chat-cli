<template>
  <section :class="styles.baseCard">
    <header v-if="$slots.header || title" :class="styles.baseCard__header">
      <slot name="header">
        <h2 :class="styles.baseCard__title">{{ title }}</h2>
        <p v-if="subtitle" :class="styles.baseCard__subtitle">{{ subtitle }}</p>
      </slot>
    </header>

    <div :class="styles.baseCard__body">
      <slot />
    </div>

    <footer v-if="$slots.footer" :class="styles.baseCard__footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<script setup lang="ts">
  defineProps<{ title?: string; subtitle?: string }>()
</script>

<style module="styles" src="./index.module.less" lang="less"></style>
