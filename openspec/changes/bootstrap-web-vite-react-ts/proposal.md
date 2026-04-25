# Proposal: Bootstrap Web Frontend (Vite + React + TS + Tailwind)

## Why

AGENTS.md §1 / §9 明确：

> Web：Vite + React 18 + TypeScript + TailwindCSS；`web/` 独立目录。
> 三大视图：登录/注册、对话、知识库。

§15 P8 要求在后端完备（Change 6/7/8/9）之后立即起前端，最终目标是 Web 上能登录、聊天（流式）、管知识库。本 change 只做**骨架 + 工具链**，具体视图在 Change 13 完成；目的是解耦"工程化搭建"与"业务实现"两步。

## What Changes

- 新增 `web/` 目录（独立子项目，Node 工程）：
  - `package.json`：Vite 5 + React 18 + TypeScript 5 + TailwindCSS 3 + pnpm。
  - `vite.config.ts`：dev proxy `/api/ → http://localhost:8000`，别名 `@ -> ./src`。
  - `tsconfig.json` + `tsconfig.node.json`：严格模式、`strictNullChecks` 等全开。
  - `tailwind.config.js` + `postcss.config.js` + `src/styles/globals.css`（tailwind base/components/utilities）。
  - `index.html` 入口。
- `src/` 基础结构（与 §2 Web 目录树对齐）：
  ```
  web/src/
  ├── main.tsx
  ├── App.tsx
  ├── router.tsx           # react-router-dom v6
  ├── app/
  │   └── providers.tsx    # QueryClientProvider + ThemeProvider
  ├── components/
  │   └── ui/              # shadcn 风格基础组件（本次先 Button/Input/Card/Spinner）
  ├── lib/
  │   ├── api.ts           # fetch wrapper（无业务）
  │   └── env.ts           # import.meta.env 封装
  ├── styles/
  │   └── globals.css
  └── pages/               # Change 13 填充真实页面
      └── Placeholder.tsx  # "hello web"
  ```
- 工程化：
  - `eslint.config.js`（flat config）：`@typescript-eslint`、`react-hooks`、`react-refresh`、`jsx-a11y`。
  - `.prettierrc`。
  - `web/package.json` scripts：`dev / build / preview / lint / format / typecheck`。
- 前后端联调：
  - Vite proxy 把 `/api/*` 转发到后端 8000；
  - `.env.development` 示例 `VITE_API_BASE=/api`。
- 补齐 `docker/web.Dockerfile`（Change 10 占位过，本 change 真正落实构建）。
- 更新 `docker-compose.override.yml`：dev 时 web 用 `pnpm dev`。
- 根 `.gitignore` 补 `web/node_modules/`、`web/dist/`。

## Non-goals

- 不写具体业务页面（Change 13 做）。
- 不接鉴权、SSE、WS 逻辑（Change 13/14 做）。
- 不引入状态管理库之外的东西（zustand / TanStack Query 在 Change 13 引入）。
- 不做 i18n。
- 不做 SSR / Next.js。

## Impact

- **新增**：`web/` 整个子项目（约 15 个小文件）。
- **修改**：`.gitignore`、`docker/web.Dockerfile`、`docker-compose.override.yml`、`README.md`。
- **依赖（JS）**：`react@18` `react-dom@18` `react-router-dom@6` `vite@5` `typescript@5` `tailwindcss@3` `postcss` `autoprefixer` `eslint@9` `@typescript-eslint/*` `eslint-plugin-react-hooks` `prettier`。
- **风险**：低。独立子项目；Python 端完全不受影响。
- **回退方式**：`rm -rf web/` + 还原 3 个被动修改。
