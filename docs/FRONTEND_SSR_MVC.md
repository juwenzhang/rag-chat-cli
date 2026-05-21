# Frontend SSR MVC Architecture

本文档记录 `websites/` 前端采用 SSR 版 MVC 的原因、痛点、边界和开发规则。

## 背景

项目从 CLI/FastAPI 演进到 Web UI 后，前端不再是单纯 CSR。当前 Web 运行链路包含：

```text
Browser
  -> Client Component
  -> Next.js Route Handler / BFF
  -> FastAPI backend

Server Component / Layout
  -> server-only API client
  -> FastAPI backend

Zustand / SSE / Cookie / BFF / Route Handler
  -> 同时参与状态和请求链路
```

这和传统 CSR/MVVM 的节奏不同。CSR 通常是：

```text
network request -> page/controller -> state/computed -> props down -> events up
```

SSR/App Router 如果没有约束，会让数据获取和业务调度分散到多个运行时，导致开发体验变差。

## 已遇到的痛点

### 1. 请求链路无感

浏览器只看到 `/api/**`，真实 FastAPI upstream path/status/body 被 BFF 包住，开发时难以判断错误来自：

- Browser -> BFF
- BFF auth/session refresh
- BFF -> FastAPI
- FastAPI business error
- SSE stream protocol

因此项目加入：

- `x-request-id` 透传。
- browser dev console `[api]` 日志。
- Next server `[upstream]` 日志。
- `ApiError.debug` 元信息。
- dev-only BFF `debug` envelope。

### 2. Server/Client 边界难判断

Next App Router 中同一个页面可能包含：

- Server Component 初始数据。
- Client Component 交互。
- BFF route handler 转发。
- Zustand store 本地状态。

没有规则时容易出现重复请求、状态不一致、误 import `server-only` 模块等问题。

### 3. View 组件混入业务逻辑

早期代码中组件内直接出现：

```ts
api.xxx(...)
toast.success(...)
router.refresh()
```

这会导致组件承担 View + Controller + Model，难以测试、复用和定位问题。

### 4. Store 混入副作用

Store 适合管理跨组件状态，但如果 store 内直接 toast/router，会让状态层承担 Controller 职责，后续应逐步迁移。

## SSR 版 MVC 映射

```text
┌──────────────────────────────┐
│ app/**/page.tsx/layout.tsx   │ Server Controller
└──────────────┬───────────────┘
               │ initial data
               ▼
┌──────────────────────────────┐
│ features/*/hooks             │ Client Controller
└──────────────┬───────────────┘
               │ view model + callbacks
               ▼
┌──────────────────────────────┐
│ features/*/components        │ View
└──────────────┬───────────────┘
               │ events
               ▼
┌──────────────────────────────┐
│ features/*/services/stores   │ Model
└──────────────────────────────┘
```

## 目录约定

```text
websites/src/
  app/                  Server Controller / BFF route handlers
  components/ui/         Pure UI
  components/shell/      Global shell

  features/<feature>/
    components/          View
    hooks/               Client Controller
    services/            Model Service
    stores/              Model State

  lib/api/
    browser/             Browser -> Next BFF
    server/              Next server -> FastAPI
    shared/              DTO / ApiError / debug metadata
```

## 各层规则

### Server Controller: `app/**`

负责：

- auth/session check
- params/searchParams
- redirect/notFound
- initial data fetch
- 调用 server API
- 把 initial props 传给 Client Controller/View

不负责：

- 大量 JSX 细节。
- browser-only API。
- UI 局部状态。

### Client Controller: `features/*/hooks`

负责：

- 调用 feature service。
- 调用 store。
- router/toast。
- autosave。
- SSE。
- optimistic update。
- conflict recovery。
- 多请求业务编排。

### View: `features/*/components`

负责：

- 渲染。
- 局部 UI state。
- props in / callbacks out。

禁止直接 import：

```ts
@/lib/api/browser
next/navigation 的 useRouter
sonner 的 toast
```

允许：

- `next/link` 声明式导航。
- input draft / dialog open / expanded / selected tab。
- DOM ref / editor ref / scroll 行为。
- copy-to-clipboard 等纯 UI 行为。

#### View component split

SSR/MVC 的 View 不应该变成超长文件。长文件会让后续维护者很难判断哪些是展示、哪些是调度，也会掩盖业务逻辑回流到 View 的问题。

约定：

- 单个 View 文件目标 `150 ~ 220` 行。
- 超过 `250` 行必须评估拆分。
- 超过 `350` 行默认必须拆。
- 优先拆 `header / toolbar / section / list / row / dialog body / form fields / footer actions`。
- 子 View 仍然必须保持 `props in / callbacks out`，不能因为拆文件而引入 `api/router/toast`。

组件族目录化：

```text
components/
  provider-card/
    index.ts
    provider-card.tsx
    provider-card-header.tsx
    provider-models-panel.tsx
```

规则：

- 一个组件族超过 2 个文件时建目录。
- `index.ts` 作为稳定导出入口，外部尽量 import 目录入口。
- parts/helpers 跟随主组件放同目录。
- `components/` 根目录只保留页面级入口、单文件小组件或跨组件族共享 View。

例外：Markdown renderer、table column config、schema/type mapping、协议解析型小工具。

### Model Service: `features/*/services`

负责：

- import `@/lib/api/browser`。
- 封装业务 API 用例。
- 做轻量参数适配。

禁止：

- React。
- router。
- toast。
- UI state。

### Model State: `features/*/stores`

负责跨组件状态：

- chat transcript / stream state。
- app shell user/org。
- wiki title overrides。
- providers page cache。

不用于：

- 单个表单。
- 单个弹窗。
- 仅单组件使用的 loading。

## API 分层

```text
lib/api/browser
  Client Component / feature service 使用。
  请求 Next `/api/**` BFF。

lib/api/server
  Server Component / Route Handler 使用。
  请求 FastAPI upstream。

lib/api/shared
  DTO、ApiError、debug metadata。
```

规则：

- View 不直接使用 `lib/api/browser`。
- Client service 使用 `lib/api/browser`。
- Server Controller 使用 `lib/api` 或 `lib/api/server/*`。
- 共享类型使用 `lib/api/shared/types`。

## 请求调试协议

每个请求应保留：

- `x-request-id`
- method
- path
- status
- duration
- sanitized body/response

开发环境查看：

1. Browser console `[api] ...`
2. Next server `[upstream] ...`
3. Response `debug` field
4. thrown `ApiError.debug`

敏感字段必须脱敏：

- password
- token
- access_token
- refresh_token
- api_key
- authorization

## 什么时候新增一层

不要为了目录整齐强行新增层。按复杂度判断：

| 场景 | 放哪里 |
|---|---|
| 单个输入框状态 | View local state |
| 单个弹窗开关 | View local state |
| 简单 API 调用 | service + page/controller callback |
| 多请求编排 | controller hook |
| 跨组件共享状态 | store |
| autosave/SSE/conflict | controller hook + service |
| server initial data | app page/layout |

## 当前迁移状态

- `lib/api` 已拆为 `browser/server/shared`。
- `providers` 已有 `services` 与 `stores`，页面 client 目前承担 controller 职责。
- `wiki` 已有 `wiki-page-service` 与 `use-wiki-page-editor`。
- `orgs`、`bookmarks` 已抽 service。
- `chat` 已有 store；后续可把 store 内 UI 副作用迁到 controller。

## 后续迭代原则

1. 新代码先遵守规则。
2. 老代码只在触碰时逐步迁移。
3. 不为了重命名制造大 diff。
4. 每次结构调整后运行：

```bash
cd websites
pnpm lint
pnpm build
```

5. 如果 View 里出现 `api/router/toast`，优先考虑抽到 service/controller。
