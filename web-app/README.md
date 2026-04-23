# web-app · rag-chat Identity Portal

Vue3 + Vite + TypeScript strict + UnoCSS + Less(CSS Modules) + Element Plus（二次封装）。

## 前置

- Node ≥ 20，pnpm ≥ 9
- 后端可选（默认走 msw mock，前端可独立演示）

## 快速开始

```bash
# 在仓库根目录
make install.web        # 或在本目录: pnpm install

# 首次生成 msw worker 到 public/（只需一次）
cd web-app && pnpm dlx msw init public/ --save && cd -

# 启动 dev server
make dev.web            # 或: pnpm --dir web-app dev
# → http://localhost:5173
```

Demo 账号：`demo@rag-chat.local / demo1234`

## 环境变量

见 `.env.example`：

| KEY | 说明 |
|---|---|
| `VITE_API_BASE_URL` | 真实后端地址（dev 模式 vite 代理到这里） |
| `VITE_USE_MOCK` | `true` 启用 msw，本地独立演示 |
| `VITE_DEFAULT_LOCALE` | `zh-CN` / `en-US` |

## 目录

```
src/
├── api/          # Axios 实例 + 各领域 API
├── components/
│   ├── base/     # ★ Element Plus 二次封装（页面禁止直接 import element-plus）
│   └── *.vue     # 业务组件
├── composables/  # Vue 组合式工具
├── i18n/         # vue-i18n
├── layouts/      # AuthLayout / AppLayout
├── mocks/        # msw handlers
├── router/       # 路由 + 登录守卫
├── stores/       # Pinia
├── styles/       # tokens.less / reset.less / element-override.less
├── types/        # api.ts / env.d.ts
└── views/        # Login / Dashboard / Token / Profile
```

## 样式三层约束

- **UnoCSS 原子类**：只做布局与一次性微调。例：`flex items-center gap-2`。
- **组件 `.module.less`**：承载结构化 BEM-ish 样式，与 template 结构一一对应。
- **`styles/*.less`**：design tokens + Element Plus 主题变量覆盖，业务组件不写全局样式。

> 详细规范见项目根 `AGENTS.md` §11b。
