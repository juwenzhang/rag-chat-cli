/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_USE_MOCK: 'true' | 'false'
  readonly VITE_DEFAULT_LOCALE: 'zh-CN' | 'en-US'
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
