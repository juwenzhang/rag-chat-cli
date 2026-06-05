# Frontend Next.js Optimization Roadmap

本文档记录 `websites/` 的 Next.js 优化方向、阶段节奏和取舍原则。目标是循序渐进地优化，而不是一次性把所有 `next.config.ts` 能开的选项都打开。

## 项目上下文

当前前端不是纯静态站点，而是：

```text
Next.js 16 / App Router / React 19
SSR Server Components
Client Components
/api/** BFF Route Handlers
cookie session
SSE chat stream
FastAPI upstream
Vercel + Docker standalone 双部署目标
```

因此优化重点不是单纯追求 Lighthouse 分数，而是同时兼顾：

- SSR 稳定性。
- BFF 请求链路可观测性。
- 安全 headers。
- Docker standalone 与 Vercel 的部署差异。
- 构建质量门禁。
- 后续性能分阶段演进。

## 总原则

1. **先安全稳定，再性能激进**。
2. **先观测，再优化**。没有数据时不要盲目开缓存或实验特性。
3. **Vercel 与自托管 Docker 分开考虑**。
4. **不要绕过 BFF**。`/api/**` 承担 auth、request-id、debug envelope，不应被 rewrite 直接替代。
5. **不要为了部署成功关闭质量门禁**。不使用 `ignoreBuildErrors` 或 `ignoreDuringBuilds`。

## 可优化维度

### 1. 部署输出

当前需要同时支持：

```text
Vercel 原生 Next 部署
Docker / VPS / Render standalone 部署
```

策略：

```ts
if (process.env.NEXT_OUTPUT_STANDALONE === "true") {
  nextConfig.output = "standalone";
}
```

原因：

- Vercel 不需要 `output: "standalone"`，由平台原生处理。
- Docker 构建需要 `.next/standalone/server.js`。
- 用环境变量切换，避免互相影响。

### 2. 安全 headers

基础安全 headers 应尽早启用：

- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy`

暂缓严格 CSP：

- TipTap / highlight / Radix / inline styles 可能被误伤。
- 后端、Vercel preview、HF backend 域名会变化。
- CSP 应先以 `Content-Security-Policy-Report-Only` 方式观测。

### 3. 压缩与响应信息

建议启用：

```ts
compress: true
poweredByHeader: false
```

收益：

- 明确开启压缩。
- 隐藏 `X-Powered-By`，减少无意义暴露。

### 4. 字体、图片与静态资源

`next/font/google` 会在构建期访问 Google Fonts。免费 CI、Docker、国内网络或 Hugging Face/Render 构建环境可能无法稳定访问，导致 `next build` 失败。

当前阶段建议：

- 使用系统字体栈作为默认字体。
- 如需品牌字体，下载字体文件后使用 `next/font/local`。
- 不在构建期依赖 Google Fonts 远程拉取。

当前项目还没有明显远程图片场景，暂不配置：

```ts
images.remotePatterns
```

后续如果引入头像、封面、外链图片，再按域名白名单配置。

不要先配置宽泛规则：

```ts
hostname: "**"
```

### 5. 缓存策略

谨慎手写 cache headers。

原因：

- Next 已经自动处理 `_next/static` 长缓存。
- SSR 页面和 BFF 数据不能粗暴缓存。
- Chat/Wiki/Providers 多数是用户态数据，缓存错会造成串数据或 stale UI。

适合后续细化：

- public share page 可评估短缓存。
- 静态 help/docs page 可评估缓存。
- `/api/**` 默认不缓存。

### 6. Rewrites / Redirects

当前不建议在 `next.config.ts` 里把 `/api/**` rewrite 到 FastAPI。

原因：

```text
Client -> Next BFF -> FastAPI
```

这条链路承载：

- server-side cookie/session。
- request-id tracing。
- debug envelope。
- upstream error normalization。

rewrite 会绕开这些边界。

### 7. Bundle 与依赖优化

后续可以关注：

- `@tiptap/*` editor 是否按页面懒加载。
- `react-markdown` / `rehype-highlight` 是否只在 message/wiki 需要时加载。
- providers/settings 页面是否避免进入 chat 首屏 bundle。
- 大型组件是否继续 view split。

这类优化优先通过 bundle analyzer 或构建数据判断，不靠直觉。

### 8. React Compiler / lint warning

当前已知 warning：

```text
src/components/ui/virtual-table.tsx
TanStack Virtual / React Compiler incompatible-library
```

这是非阻断 warning。后续可以：

- 单独隔离 virtual table。
- 确认是否需要对该组件禁用 compiler memoization。
- 或等待 TanStack/React Compiler 兼容性改进。

### 9. Typed routes

`typedRoutes` 可以提升路由类型安全，但建议后置。

原因：

- 当前动态路由多。
- 刚完成目录迁移和 view split。
- 立刻开启可能引入大量类型调整。

适合阶段：路由结构稳定后再评估。

### 10. Strict CSP

建议最后做。

阶段策略：

1. 先整理所有外部域名：Vercel、HF backend、未来图片/CDN。
2. 先上 `Content-Security-Policy-Report-Only`。
3. 收集违规。
4. 再切换为强制 CSP。

## 分阶段路线

### Phase 0：当前立刻做

目标：低风险、不会影响业务。

- 保留条件 `standalone`。
- 启用 `compress`。
- 禁用 `poweredByHeader`。
- 增加基础安全 headers。
- 移除构建期依赖外网的 `next/font/google`，优先使用系统字体或本地字体。
- 不改 rewrites/cache/CSP。
- `pnpm lint`、`pnpm build` 必须通过。

### Phase 1：部署稳定后

目标：让 Vercel + 后端 + BFF 链路稳定。

- 明确 `RAG_API_URL`、`SESSION_COOKIE_SECURE`、`APP_CORS_ORIGINS` 文档。
- 验证 SSR 页面、登录、BFF route handlers、SSE streaming。
- 检查前端请求 debug 是否能串起 requestId。
- 观察 HF/后端冷启动对前端 UX 的影响。

### Phase 2：性能观测

目标：拿数据再优化。

- 引入 bundle analyzer 或构建分析脚本。
- 分析 chat/wiki/providers 首屏 bundle。
- 检查 TipTap、Markdown、highlight 是否需要动态加载。
- 针对具体页面做 code splitting。

### Phase 3：缓存与资源策略

目标：细粒度优化而不是全局缓存。

- 对 public share page 评估缓存。
- 对静态 assets 保持 Next 默认策略。
- 对用户态 `/api/**` 保持 no-store。
- 如需图片，配置精确 `images.remotePatterns`。

### Phase 4：类型与安全强化

目标：路由和浏览器安全策略增强。

- 评估 `typedRoutes`。
- 增加 CSP Report-Only。
- 逐步收紧 CSP。
- 针对 frame/embed/share 页面做更细策略。

### Phase 5：生产化部署

目标：自托管/VPS 生产体验。

- Docker standalone + Nginx。
- gzip/brotli 由 Nginx/CDN 接管。
- health check 与 release rollback。
- 前后端 request-id 全链路日志。

## 当前不做的事

不要在当前阶段添加：

```ts
typescript: { ignoreBuildErrors: true }
eslint: { ignoreDuringBuilds: true }
```

不要当前阶段添加：

```ts
rewrites() { return [{ source: "/api/:path*", destination: "..." }] }
```

不要当前阶段添加严格 CSP。

不要当前阶段开启所有实验特性。

## 推荐当前 `next.config.ts` 基线

```ts
import type { NextConfig } from "next";

const isStandalone = process.env.NEXT_OUTPUT_STANDALONE === "true";

const nextConfig: NextConfig = {
  compress: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
          },
        ],
      },
    ];
  },
};

if (isStandalone) {
  nextConfig.output = "standalone";
}

export default nextConfig;
```

后续所有新增优化都应该先判断属于哪个 phase，再落地。
