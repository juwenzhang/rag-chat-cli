<template>
  <BaseCard :class="styles.profile" :title="t('profile.title')">
    <dl :class="styles.profile__list">
      <div :class="styles.profile__row">
        <dt :class="styles.profile__label">{{ t('profile.email') }}</dt>
        <dd :class="styles.profile__value">{{ auth.user?.email ?? '-' }}</dd>
      </div>
      <div :class="styles.profile__row">
        <dt :class="styles.profile__label">{{ t('profile.displayName') }}</dt>
        <dd :class="styles.profile__value">{{ auth.user?.display_name ?? '-' }}</dd>
      </div>
      <div :class="styles.profile__row">
        <dt :class="styles.profile__label">{{ t('profile.scope') }}</dt>
        <dd :class="styles.profile__value">{{ (auth.user?.scope ?? []).join(', ') || '-' }}</dd>
      </div>
      <div :class="styles.profile__row">
        <dt :class="styles.profile__label">{{ t('profile.createdAt') }}</dt>
        <dd :class="styles.profile__value">{{ auth.user?.created_at ?? '-' }}</dd>
      </div>
    </dl>
  </BaseCard>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import { useAuthStore } from '@/stores/auth'
  import BaseCard from '@/components/base/BaseCard'

  const { t } = useI18n()
  const auth = useAuthStore()
</script>

<style module="styles" src="./index.module.less" lang="less"></style>
