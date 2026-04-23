import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export type Theme = 'dark' | 'light'

export const useUiStore = defineStore('ui', () => {
  const theme = ref<Theme>((localStorage.getItem('rag_chat_theme') as Theme) || 'dark')

  function applyTheme(t: Theme): void {
    document.documentElement.setAttribute('data-theme', t)
    localStorage.setItem('rag_chat_theme', t)
  }

  watch(theme, applyTheme, { immediate: true })

  function toggle(): void {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  return { theme, toggle }
})
