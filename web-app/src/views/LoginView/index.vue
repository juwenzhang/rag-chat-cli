<template>
  <BaseCard
    :class="styles.loginView"
    :title="t('auth.login.title')"
    :subtitle="t('auth.login.subtitle')"
  >
    <form :class="styles.loginView__form" @submit.prevent="onSubmit">
      <BaseEmailField v-model="email" required :error="emailError" />
      <BasePasswordField v-model="password" required :error="passwordError" />

      <p v-if="serverError" :class="styles.loginView__serverError">{{ serverError }}</p>

      <BaseButton
        variant="primary"
        native-type="submit"
        :loading="loading"
        :class="styles.loginView__submit"
      >
        {{ loading ? t('auth.login.submitting') : t('auth.login.submit') }}
      </BaseButton>

      <p :class="styles.loginView__demo">demo: demo@rag-chat.local / demo1234</p>
    </form>
  </BaseCard>
</template>

<script setup lang="ts">
  import { ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { z } from 'zod'
  import { useAuthStore } from '@/stores/auth'
  import { AppError } from '@/api/http'
  import BaseCard from '@/components/base/BaseCard'
  import BaseButton from '@/components/base/BaseButton'
  import BaseEmailField from '@/components/base/BaseEmailField'
  import BasePasswordField from '@/components/base/BasePasswordField'

  const { t } = useI18n()
  const auth = useAuthStore()
  const router = useRouter()
  const route = useRoute()

  const email = ref('')
  const password = ref('')
  const emailError = ref('')
  const passwordError = ref('')
  const serverError = ref('')
  const loading = ref(false)

  const schema = z.object({
    email: z.string().email(),
    password: z.string().min(8),
  })

  async function onSubmit(): Promise<void> {
    emailError.value = ''
    passwordError.value = ''
    serverError.value = ''

    const parsed = schema.safeParse({ email: email.value, password: password.value })
    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        if (issue.path[0] === 'email') emailError.value = issue.message
        if (issue.path[0] === 'password') passwordError.value = issue.message
      }
      return
    }

    loading.value = true
    try {
      await auth.login({ email: email.value, password: password.value })
      const redirect = (route.query.redirect as string) || '/dashboard'
      router.replace(redirect)
    } catch (e) {
      if (e instanceof AppError && e.status === 401) {
        serverError.value = t('auth.login.errorInvalidCredentials')
      } else {
        serverError.value = t('auth.login.errorNetwork')
      }
    } finally {
      loading.value = false
    }
  }
</script>

<style module="styles" src="./index.module.less" lang="less"></style>
