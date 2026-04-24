# Design: Bootstrap Web Frontend

## Context

AGENTS.md §9 / §15 P8 把 Web 作为最后一块拼图。后端已具备完整 REST + SSE + WS 能力；Web 作为唯一 GUI 入口（CLI 仍保留），需要与 CLI **对齐视觉语言**（AGENTS.md §3.9：CLI 取向 opencode → 明暗双主题、sans-serif、模糊边界）。

## Goals / Non-Goals

**Goals**
- **最小可运行骨架**：`pnpm dev` 起本地；浏览器看到 placeholder 页。
- **严格类型**：`tsconfig.json` 开 `strict / noUncheckedIndexedAccess / exactOptionalPropertyTypes`。
- **Tailwind 设计 token**：色板/字体与 CLI 主题可互为镜像（本 change 先定义 CSS 变量 + Tailwind 映射，具体值对齐 Change 2 的 `theme.toml`）。
- **一键构建**：`pnpm build` 产物 < 500KB gzipped 的基线（本期组件少，预计远小于）。
- **联调友好**：Vite dev proxy 让前端直接 `fetch("/api/me")` 无 CORS。

**Non-Goals**
- 不做设计系统组件全集（shadcn/radix 引入后续 change）。
- 不做 PWA。
- 不做 monorepo（web 与 Python 同仓，`web/` 即子目录）。

## Architecture

### `web/package.json`

```json
{
  "name": "rag-chat-web",
  "private": true,
  "type": "module",
  "version": "0.1.0",
  "packageManager": "pnpm@9.5.0",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview --port 4173",
    "lint": "eslint . --max-warnings=0",
    "lint:fix": "eslint . --fix",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "typecheck": "tsc -b --noEmit"
  }
}
```

### `web/vite.config.ts`

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL ?? "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
        ws: true,           // WS 转发
      },
    },
  },
});
```

### `web/tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "jsx": "react-jsx",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "useDefineForClassFields": true,
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "forceConsistentCasingInFileNames": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

### Tailwind 设计 token（CSS variables → Tailwind）

`src/styles/globals.css`：

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bg: #f7f7f5;
  --fg: #1a1a19;
  --muted: #7a7a76;
  --accent: #e6a23c;    /* 与 CLI opencode 暖色一致 */
  --border: #e5e5e0;
  --radius: 8px;
  --font-sans: Inter, "PingFang SC", system-ui, sans-serif;
}
[data-theme="dark"] {
  --bg: #1a1a19;
  --fg: #f0f0ea;
  --muted: #8a8a82;
  --accent: #e6a23c;
  --border: #2b2b28;
}

html, body, #root { height: 100%; background: var(--bg); color: var(--fg); font-family: var(--font-sans); }
```

`tailwind.config.js`：

```js
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        fg: "var(--fg)",
        muted: "var(--muted)",
        accent: "var(--accent)",
        border: "var(--border)",
      },
      borderRadius: { DEFAULT: "var(--radius)" },
      fontFamily: { sans: "var(--font-sans)" },
    },
  },
  darkMode: ["class", '[data-theme="dark"]'],
  plugins: [],
};
```

### 骨架页

`src/main.tsx`：

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/App";
import "@/styles/globals.css";

createRoot(document.getElementById("root")!).render(<StrictMode><App/></StrictMode>);
```

`src/App.tsx`：返回 `<RouterProvider router={router} />`。

`src/router.tsx`：暂时只配 `/` → `Placeholder`。

`src/pages/Placeholder.tsx`：

```tsx
export function Placeholder() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-4">
      <h1 className="text-3xl font-semibold">rag-chat</h1>
      <p className="text-muted">web frontend bootstrap ok</p>
      <button className="border border-border rounded px-4 py-2 hover:bg-border/30"
              onClick={() => document.documentElement.dataset.theme =
                document.documentElement.dataset.theme === "dark" ? "light" : "dark"}>
        toggle theme
      </button>
    </main>
  );
}
```

### `src/lib/api.ts`（仅 wrapper，业务 Change 13 再加）

```ts
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${import.meta.env.VITE_API_BASE ?? "/api"}${path}`, {
    headers: { "content-type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json() as Promise<T>;
}
export class ApiError extends Error { constructor(public status: number, public body: string) { super(`${status}: ${body}`); } }
```

### `eslint.config.js`（flat）

```js
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: { parserOptions: { project: "./tsconfig.json", tsconfigRootDir: import.meta.dirname } },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "@typescript-eslint/consistent-type-imports": "warn",
    },
  },
);
```

### `docker/web.Dockerfile`（真正落地）

见 Change 10 design；本 change 确认 `web/` 源码存在后才能 build 成功：

```dockerfile
FROM node:20-alpine AS builder
RUN corepack enable
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/. .
RUN pnpm build

FROM nginx:1.27-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /web/dist /usr/share/nginx/html
```

## Alternatives Considered

- **Next.js**：功能强大但重；本期 SPA + Vite 足够，可避免 SSR 带来的复杂度。
- **Create React App**：已废弃，不考虑。
- **SWC vs Babel**：`@vitejs/plugin-react` 默认 Babel；可切 `@vitejs/plugin-react-swc` 提速，本期 default 够。

## Risks & Mitigations

- **风险**：pnpm 版本不固定导致锁文件冲突。
  **缓解**：`packageManager` 字段 + Corepack + CI `corepack enable`。
- **风险**：Vite proxy 对 WS 支持需特殊配置。
  **缓解**：`ws: true` 已开，Change 13 真正联调时验证。
- **风险**：Tailwind class bundle 膨胀。
  **缓解**：`content` 只包含 `src/**` + `index.html`；JIT 自动 purge。

## Testing Strategy

- **构建**：
  - `pnpm install && pnpm build` 成功；`dist/index.html` 产物存在。
  - `pnpm preview` 打开浏览器，placeholder 页正常、主题切换工作。
- **联调**：
  - `python main.py serve` + `pnpm dev`：浏览器 Network 面板 `/api/health` 返回 200（经过 Vite proxy）。
- **容器化**：
  - `docker build -f docker/web.Dockerfile -t ragchat-web:test .` 成功。
  - `docker compose --profile full up -d` 后 `curl http://localhost/` 拿到 placeholder HTML。
- **类型与 Lint**：
  - `pnpm typecheck` 无错。
  - `pnpm lint` 无警告。
