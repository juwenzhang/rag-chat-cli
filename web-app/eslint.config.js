import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import vueTsConfig from '@vue/eslint-config-typescript'
import prettierSkip from '@vue/eslint-config-prettier/skip-formatting'

export default [
  { ignores: ['dist', 'node_modules', 'auto-imports.d.ts', 'components.d.ts'] },
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  ...vueTsConfig(),
  prettierSkip,
  {
    rules: {
      'vue/multi-word-component-names': 'off',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      // ★ 页面禁止直接 import Element Plus；必须通过 base/ 二次封装
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: 'element-plus',
              message:
                'Do not import element-plus directly. Use wrapped components in src/components/base/.',
            },
          ],
          patterns: [
            {
              group: ['element-plus/*'],
              message:
                'Do not import element-plus/* directly. Use wrapped components in src/components/base/.',
            },
          ],
        },
      ],
    },
  },
  {
    // 仅在 base/ 目录下允许 import element-plus
    files: ['src/components/base/**'],
    rules: { 'no-restricted-imports': 'off' },
  },
]
