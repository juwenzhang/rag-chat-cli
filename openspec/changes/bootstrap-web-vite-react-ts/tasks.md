# Tasks: Bootstrap Web Frontend

## 1. 工具链先决

- [ ] 1.1 本机 Node ≥ 20，`corepack enable`。
- [ ] 1.2 确认 pnpm 能用：`pnpm -v`。

## 2. 初始化 `web/` 工程

- [ ] 2.1 `mkdir web && cd web`。
- [ ] 2.2 `pnpm create vite@latest . --template react-ts`（交互选 react/ts，已有目录允许）。
- [ ] 2.3 调整 `package.json` 的 `name/version/packageManager/scripts`（按 design）。
- [ ] 2.4 删除 Vite 模板自带的示例 logo、`App.css`、`src/assets/`。

## 3. Vite 配置

- [ ] 3.1 写 `vite.config.ts`（proxy + alias + ws）。
- [ ] 3.2 `vite` 开发服务器 `pnpm dev` 起在 5173。
- [ ] 3.3 `tsconfig.json` 更新为 design 版本（严格 + paths）。
- [ ] 3.4 `tsconfig.node.json`：为 `vite.config.ts` 专用 compile 选项。

## 4. Tailwind

- [ ] 4.1 `pnpm add -D tailwindcss postcss autoprefixer`。
- [ ] 4.2 `pnpm exec tailwindcss init -p` 生成 `tailwind.config.js / postcss.config.js`。
- [ ] 4.3 覆盖 `tailwind.config.js` 按 design。
- [ ] 4.4 新建 `src/styles/globals.css`，`src/main.tsx` import。
- [ ] 4.5 启动 `pnpm dev`，确认 Tailwind utility 生效（`<div class="text-accent">...</div>` 颜色正确）。

## 5. 基础组件 + 骨架页

- [ ] 5.1 `src/components/ui/button.tsx`：`<Button variant primary|ghost|danger>`。
- [ ] 5.2 `src/components/ui/input.tsx`：受控 input，带 error state。
- [ ] 5.3 `src/components/ui/card.tsx`：简单 Card（border + padding + radius）。
- [ ] 5.4 `src/components/ui/spinner.tsx`：纯 CSS spinner。
- [ ] 5.5 `src/pages/Placeholder.tsx`：按 design。
- [ ] 5.6 `src/App.tsx` + `src/router.tsx`：`react-router-dom@6` `createBrowserRouter`。
- [ ] 5.7 `src/app/providers.tsx`：占位（本期无 provider，Change 13 注入）。

## 6. API 封装

- [ ] 6.1 `src/lib/env.ts`：`export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";`。
- [ ] 6.2 `src/lib/api.ts`：`api()` + `ApiError`（按 design）。
- [ ] 6.3 类型：定义 `ApiSuccess<T>` / `ApiErrorBody` 最简形（详细 schema Change 13 再用 openapi-typescript 生成）。

## 7. ESLint + Prettier

- [ ] 7.1 `pnpm add -D eslint @eslint/js typescript-eslint eslint-plugin-react-hooks eslint-plugin-react-refresh prettier`。
- [ ] 7.2 新建 `eslint.config.js`（flat，按 design）。
- [ ] 7.3 新建 `.prettierrc`（简单配置：`singleQuote: false`，`semi: true`，`printWidth: 100`）。
- [ ] 7.4 新建 `.prettierignore` 排除 `dist`。
- [ ] 7.5 `pnpm lint` 无错；`pnpm format:check` 无错。

## 8. 环境变量

- [ ] 8.1 `web/.env.development`：`VITE_API_BASE=/api`。
- [ ] 8.2 `web/.env.example`：同上。
- [ ] 8.3 在 `README.md` web 章节说明 env 用法。

## 9. Docker & compose 落地

- [ ] 9.1 `docker/web.Dockerfile` 按 design 写（`WITH_WEB` 不再需要，直接 COPY web/）。
- [ ] 9.2 `docker-compose.override.yml` 的 `web` 在 dev 场景下：
  ```yaml
  web:
    image: node:20-alpine
    working_dir: /web
    command: sh -c "corepack enable && pnpm install && pnpm dev --host 0.0.0.0"
    volumes: ["./web:/web"]
    ports: ["5173:5173"]
  ```
- [ ] 9.3 `docker compose --profile full up -d --build` 验证 web 能构建、nginx 能托管 `dist/`。

## 10. .gitignore

- [ ] 10.1 补：`web/node_modules/`、`web/dist/`、`web/.vite/`、`web/*.log`、`web/.env.local`。

## 11. 父层 Makefile 追加

- [ ] 11.1 根 `Makefile` 新增 `web-dev / web-build / web-lint / web-typecheck` 代理到 `(cd web && pnpm ...)`。
- [ ] 11.2 `make ci` 扩展：在原先 `lint typecheck test-cov openapi-check` 之后追加 `web-lint web-typecheck web-build`。

## 12. CI 接入

- [ ] 12.1 `.github/workflows/ci.yml` 新增 `web` job：
  ```yaml
  web:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: corepack enable
      - run: pnpm -v
      - working-directory: web
        run: |
          pnpm install --frozen-lockfile
          pnpm lint
          pnpm typecheck
          pnpm build
  ```
- [ ] 12.2 `docker-build` job 扩展：同时 build `docker/web.Dockerfile`。

## 13. 文档

- [ ] 13.1 `README.md` 新增 "Web" 章节：`cd web && pnpm install && pnpm dev`。
- [ ] 13.2 `docs/DEVELOPMENT.md` 补"前端工作流"章节。
- [ ] 13.3 AGENTS.md §19 追加 "Web bootstrap"。

## 14. 冒烟

- [ ] 14.1 `cd web && pnpm install && pnpm dev`：浏览器 `http://localhost:5173` 能看到 placeholder 页；点击按钮主题切换正常。
- [ ] 14.2 `pnpm build` 成功，`dist/index.html` 存在。
- [ ] 14.3 同时起 `python main.py serve`：在 placeholder 加一个 `fetch("/api/health")` 临时调用，浏览器 Network 面板 200 OK。
- [ ] 14.4 `docker compose --profile full up -d --build`：`curl http://localhost/` 返回构建后的 html。
- [ ] 14.5 `pnpm lint && pnpm typecheck` 全绿。
