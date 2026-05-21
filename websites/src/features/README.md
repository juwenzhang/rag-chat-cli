# Frontend Feature Architecture

本目录采用适配 Next.js App Router / SSR 的轻量 MVC 约定。目标不是为了抽象而抽象，而是把 SSR 带来的多运行环境心智负担压回到接近 CSR/MVVM 的开发节奏：**数据和调度集中，组件只渲染和抛事件**。

## 为什么需要这套规则

以前 CSR 开发通常是：

```text
网络请求 -> page/controller -> state/computed/memo -> props 下发 -> 组件 emit 事件
```

Next.js SSR/App Router 多了运行边界：

```text
Server Component
Client Component
Route Handler / BFF
Browser runtime
FastAPI backend
Zustand store
SSE stream
```

如果没有规则，代码会很快变成：

- Server Component 里取一次数据，Client Component 里又取一次。
- View 组件里直接 `api`、`toast`、`router`。
- Store 里混业务提示和跳转。
- BFF 屏蔽了真实后端错误，调试请求链路困难。
- SSR 与 CSR 状态边界不清，导致改动位置难判断。

所以本项目采用 SSR 版 MVC：

```text
app/**             = Server Controller
features/*/hooks   = Client Controller
features/*/services = Model Service
features/*/stores  = Model State
features/*/components = View
components/ui      = Pure UI
```

## 数据流

```text
┌──────────────────────────────┐
│ app/**/page.tsx/layout.tsx   │ Server Controller
│ - auth                       │
│ - params/searchParams        │
│ - initial fetch              │
│ - redirect/notFound          │
└──────────────┬───────────────┘
               │ initial props
               ▼
┌──────────────────────────────┐
│ features/*/hooks             │ Client Controller
│ - call service/store         │
│ - router/toast               │
│ - event orchestration        │
└──────────────┬───────────────┘
               │ view model + callbacks
               ▼
┌──────────────────────────────┐
│ features/*/components        │ View
│ - render                     │
│ - local UI state             │
│ - callback only              │
└──────────────┬───────────────┘
               │ user events
               ▼
┌──────────────────────────────┐
│ features/*/services/stores   │ Model
│ - API use cases              │
│ - client state               │
└──────────────────────────────┘
```

## 目录职责

### `components/` = View

组件负责渲染和局部 UI 交互。

允许：

- `useState` 管理弹窗开关、输入框 draft、hover、expanded、selected tab。
- `useMemo` 做纯展示派生，例如本地搜索过滤。
- `useRef` 做 DOM/滚动/编辑器实例引用。
- 通过 props 接收数据，通过 callback 抛事件。

禁止：

- 直接 import `@/lib/api/browser`。
- 直接 import `useRouter` 做业务跳转。
- 直接 import `toast` 做业务提示。
- 编排多请求流程、autosave、SSE、revision conflict、权限型业务流程。

例外：

- `next/link` 可以用于声明式导航。
- 剪贴板、焦点、滚动等浏览器 UI 行为可以留在 View。

### View component split

View 可以继续拆小组件，这不是增加业务抽象，而是降低维护成本。

建议：

- 单个 View 文件目标控制在 `150 ~ 220` 行。
- 超过 `250` 行必须评估拆分。
- 超过 `350` 行默认必须拆分。
- 优先拆 header、toolbar、list、row、dialog body、form fields、empty state、footer actions。
- 拆分时保持 `props in / callbacks out`，不要把 API、router、toast 顺手塞进子 View。

目录化规则：

- 一个组件族超过 2 个文件时，优先建同名目录，例如 `provider-card/`、`model-selector/`。
- 目录内保留主文件，例如 `provider-card/provider-card.tsx`。
- 目录内提供 `index.ts` 作为稳定导出入口。
- 组件族内部的 parts/helpers 放同目录，避免散落在 `components/` 根目录。
- `components/` 根目录只放页面级入口、单文件小组件或跨组件族共享 View。

例外：

- Markdown renderer。
- table column/schema/config 映射。
- 类型密集或协议解析型工具文件。

### `hooks/` = Client Controller

Controller 负责把事件变成业务动作。

允许：

- 调用 `services`。
- 调用 `stores`。
- 使用 `useRouter`。
- 使用 `toast`。
- 编排 autosave、SSE、optimistic update、错误恢复、跳转。

不建议：

- 写大量 JSX。
- 放纯 UI 组件实现。

### `services/` = Model Service

Service 负责业务 API 用例，是组件和 `lib/api/browser` 的隔离层。

允许：

- import `@/lib/api/browser`。
- 封装业务动作，例如 `deletePage`、`createShare`、`updateProvider`。
- 做轻量参数适配。

禁止：

- import React。
- import `next/navigation`。
- import `sonner`。
- 直接操作 UI state。

### `stores/` = Model State

Store 管跨组件客户端状态。

适合：

- Chat stream/transcript。
- Wiki sidebar title overrides。
- App shell user/org state。
- Provider list/preferences 这类页面级 server state 缓存。

不适合：

- 单个表单 draft。
- 单个弹窗 open/close。
- 只在一个组件内部使用的 loading 状态。

严格 MVC 下，store 不应直接 `toast` 或 `router`；复杂历史代码可逐步迁移到 controller。

## `lib/api` 边界

```text
lib/api/browser  浏览器 -> Next BFF
lib/api/server   Next Server/Route Handler -> FastAPI
lib/api/shared   DTO / ApiError / debug metadata
```

规则：

- Client Component / feature service 只能 import `@/lib/api/browser`。
- Server Component / Route Handler 只能 import `@/lib/api` 或 `@/lib/api/server/*`。
- 两端共享类型从 `@/lib/api/shared/types` 引入。
- 不要从 View 直接 import `@/lib/api/browser`。

## 新功能落地检查清单

写新功能时按顺序判断：

1. 初始数据能否在 `app/**/page.tsx` Server Controller 获取？
2. 用户事件是否需要 Client Controller hook 承接？
3. 是否有 API 调用？有则先放 `services/`。
4. 是否跨组件共享状态？有则放 `stores/`，否则留局部 state。
5. View 是否只接收 props 和 callbacks？
6. View 是否没有 `api/router/toast`？
7. 请求链路是否能通过 dev debug 日志看到 requestId、status、duration？

## 当前迁移状态

- `chat`：已有 store，后续可把 store 内 toast 逐步迁到 controller。
- `wiki`：已有 service 和 `use-wiki-page-editor` controller，sidebar 仍可继续拆 controller/view。
- `providers`：已有 service/store，`providers-page-client` 当前承担 controller 职责。
- `orgs`、`bookmarks`：已有 service，页面仍是 controller + view 混合，后续按需拆。

## 核心原则

> 高复杂模块深拆，低复杂模块浅拆；但 View 永远不要直接承接业务请求。
