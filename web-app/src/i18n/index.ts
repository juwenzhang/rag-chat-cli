import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN.json'
import enUS from './locales/en-US.json'

type Messages = typeof zhCN
export type LocaleKey = 'zh-CN' | 'en-US'

const fallback: LocaleKey = 'zh-CN'
const initial = (import.meta.env.VITE_DEFAULT_LOCALE as LocaleKey) || fallback

export const i18n = createI18n<[Messages], LocaleKey>({
  legacy: false,
  locale: initial,
  fallbackLocale: fallback,
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
  },
})
