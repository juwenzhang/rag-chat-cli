import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import UnoCSS from 'unocss/vite'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import VueDevTools from 'vite-plugin-vue-devtools'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiBase = env.VITE_API_BASE_URL || 'http://localhost:8000'

  return {
    plugins: [
      vue(),
      UnoCSS(),
      VueDevTools(),
      // 自动导入 Vue / Pinia / Router 的 composition API
      AutoImport({
        imports: ['vue', 'vue-router', 'pinia', '@vueuse/core'].filter(
          // @vueuse/core 未装时自动忽略
          (pkg) => {
            try {
              require.resolve(pkg)
              return true
            } catch {
              return false
            }
          },
        ) as Array<'vue' | 'vue-router' | 'pinia'>,
        dts: 'auto-imports.d.ts',
        eslintrc: { enabled: true },
      }),
      // ★ 只在 base/ 目录下自动解析 Element Plus，避免页面直接裸用
      Components({
        dirs: ['src/components/base'],
        resolvers: [ElementPlusResolver({ importStyle: 'css' })],
        dts: 'components.d.ts',
      }),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    css: {
      preprocessorOptions: {
        less: {
          additionalData: `@import "@/styles/tokens.less";`,
          javascriptEnabled: true,
        },
      },
      modules: {
        generateScopedName: '[name]__[local]__[hash:base64:5]',
        localsConvention: 'camelCaseOnly',
      },
    },
    server: {
      host: '0.0.0.0',
      port: 5177,
      proxy: {
        '/api': { target: apiBase, changeOrigin: true },
        '/ws': { target: apiBase.replace(/^http/, 'ws'), ws: true, changeOrigin: true },
      },
    },
    build: {
      target: 'es2022',
      sourcemap: true,
    },
  }
})
