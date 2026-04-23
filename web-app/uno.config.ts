import {
  defineConfig,
  presetAttributify,
  presetIcons,
  presetUno,
  transformerDirectives,
  transformerVariantGroup,
} from 'unocss'

export default defineConfig({
  // 只扫模板与样式，不扫纯 TS/JS 逻辑文件，避免 `return` / `if` 等关键字被当 icon
  content: {
    pipeline: {
      include: [
        'index.html',
        'src/**/*.vue',
        'src/**/*.html',
      ],
      exclude: [
        'node_modules',
        '.git',
        'dist',
        // 显式排除纯 TS/JS，防止源码 token 被扫为 class
        'src/**/*.{ts,tsx,js,jsx}',
      ],
    },
  },
  presets: [
    presetUno(),
    // attributify 只识别带 u- 前缀的属性，避免 `return` / `function` 等被当成原子类
    presetAttributify({ prefix: 'u-', prefixedOnly: true }),
    presetIcons({
      scale: 1.1,
      // 只认 i- 前缀，且不加载时给 warn，不中断
      prefix: ['i-'],
      warn: true,
    }),
  ],
  transformers: [transformerDirectives(), transformerVariantGroup()],
  theme: {
    colors: {
      // 与 src/styles/tokens.less 保持同源
      bg: {
        base: 'var(--color-bg)',
        surface: 'var(--color-surface)',
        elevated: 'var(--color-surface-2)',
      },
      border: {
        DEFAULT: 'var(--color-border)',
        strong: 'var(--color-border-strong)',
      },
      text: {
        primary: 'var(--color-text-primary)',
        secondary: 'var(--color-text-secondary)',
        muted: 'var(--color-text-muted)',
      },
      brand: {
        DEFAULT: 'var(--color-primary)',
        hover: 'var(--color-primary-hover)',
      },
      success: 'var(--color-success)',
      warning: 'var(--color-warning)',
      danger: 'var(--color-danger)',
    },
    fontFamily: {
      mono: 'var(--font-mono)',
      sans: 'var(--font-sans)',
    },
  },
  // 动态拼接/条件用到的 icon，放 safelist 保证生成
  safelist: [
    'i-lucide-copy',
    'i-lucide-check',
    'i-lucide-log-out',
    'i-lucide-sun',
    'i-lucide-moon',
    'i-lucide-inbox',
    'i-lucide-message-square-code',
  ],
})
