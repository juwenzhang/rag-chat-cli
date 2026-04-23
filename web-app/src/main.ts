import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { i18n } from './i18n'
import { useAuthStore } from './stores/auth'

// 注意顺序：
// 1) 第三方库 CSS 先
// 2) UnoCSS 原子类（后加载，优先级更高，能盖掉 Element Plus 的默认样式）
// 3) 项目自己的 reset/主题覆盖最后
import 'element-plus/dist/index.css'
import 'virtual:uno.css'
import '@/styles/reset.less'
import '@/styles/element-override.less'

async function bootstrap() {
  if (import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === 'true') {
    const { worker } = await import('./mocks/browser')
    await worker.start({ onUnhandledRequest: 'bypass' })
    // eslint-disable-next-line no-console
    console.info('[mock] msw worker started')
  }

  const app = createApp(App)
  const pinia = createPinia()

  app.use(pinia)
  app.use(router)
  app.use(i18n)

  useAuthStore().restore()

  app.mount('#app')
}

bootstrap()
