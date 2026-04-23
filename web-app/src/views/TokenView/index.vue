<template>
  <div :class="styles.tokenView">
    <TokenCard />
  </div>
</template>

<script setup lang="ts">
  import TokenCard from '@/components/TokenCard'
</script>

<style module="styles" src="./index.module.less" lang="less"></style>
