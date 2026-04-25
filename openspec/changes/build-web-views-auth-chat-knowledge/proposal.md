# Proposal: Build Web Views (Auth / Chat / Knowledge)

## Why

AGENTS.md §9 明确 Web 三大视图：

> - **登录/注册**：邮箱 + 密码。
> - **对话**：左侧 session 列表，右侧消息流，SSE/WS 流式渲染 retrieval 卡片 + token delta + done usage。
> - **知识库**：列表 + 上传（拖拽或表单）+ reindex 按钮 + 搜索。

Change 12 搭完骨架，本 change 把三大视图落实 —— 这是"Web 化"的核心价值交付。

## What Changes

### 依赖新增（web）
- `@tanstack/react-query@5`（数据管线，缓存、重试、mutation）。
- `zustand@4`（全局轻量状态：token、theme、currentSessionId）。
- `react-hook-form@7` + `zod@3` + `@hookform/resolvers`（表单 + 校验）。
- `openapi-typescript@6`（从 `docs/openapi.json` 生成类型）。
- `react-markdown@9` + `remark-gfm` + `rehype-highlight`（消息 Markdown）。
- `lucide-react`（图标）。
- `sonner`（toast 通知）。

### 目录结构（补齐 §2 Web 结构）

```
web/src/
├── app/providers.tsx           # QueryClient + Zustand hydration + ThemeProvider + Toaster
├── features/
│   ├── auth/
│   │   ├── AuthStore.ts        # zustand: token, user, login, logout, refresh
│   │   ├── LoginPage.tsx
│   │   ├── RegisterPage.tsx
│   │   ├── ProtectedRoute.tsx
│   │   └── useAuthTokenBootstrap.ts   # 启动时从 localStorage 读 token + /me
│   ├── chat/
│   │   ├── ChatLayout.tsx       # 左右两栏
│   │   ├── SessionSidebar.tsx   # 会话列表 + 新建
│   │   ├── MessageList.tsx
│   │   ├── MessageBubble.tsx    # user / assistant 样式
│   │   ├── RetrievalCard.tsx
│   │   ├── StreamingMessage.tsx # SSE/WS 逐字渲染
│   │   ├── ChatInput.tsx        # 多行输入 + RAG toggle
│   │   └── useChatStream.ts     # 选择 SSE 或 WS 的 hook
│   └── knowledge/
│       ├── KnowledgePage.tsx
│       ├── DocumentList.tsx
│       ├── UploadDropzone.tsx
│       ├── SearchBar.tsx
│       └── ReindexButton.tsx
├── lib/
│   ├── api.ts                   # 扩展：带 Authorization header
│   ├── apiClient.ts             # 从 openapi-typescript 生成 Client
│   ├── sse.ts                   # fetch-based SSE reader
│   ├── ws.ts                    # WebSocket 封装
│   └── types.ts                 # 从生成类型 re-export
├── components/ui/               # 补：Textarea / Avatar / Dialog / Tabs / Tooltip
├── router.tsx                   # 注册 /login /register /chat /knowledge 路由
└── main.tsx                     # 不变
```

### 路由

- `/login` / `/register`：未登录入口。
- `/chat`（默认路由，`/` 重定向）：对话页，登录后才可访问。
- `/chat/:sessionId`：特定会话。
- `/knowledge`：知识库管理。
- `/404`：兜底。

### 关键行为

- 启动时 `useAuthTokenBootstrap`：从 `localStorage.ragchat_token` 读 → `GET /me` 验证 → 失败则走 refresh → 再失败清 token 跳 `/login`。
- `ChatInput` 发送：
  - 默认用 **WS**（双向，支持 abort）；
  - 若 `VITE_STREAM=sse` 或 WS 失败回退 SSE（`fetch` + body reader）。
  - 事件消费走 `api/streaming/protocol.py` 对应的 TS 类型（通过 openapi-typescript 生成）。
- `RetrievalCard`：可折叠，显示 `[n]` hit 列表。
- `UploadDropzone`：文本文件 `text/markdown, text/plain`；大小 < 10MB。
- `SearchBar`：输入即 debounce 300ms 调 `GET /knowledge/search`。

### 鉴权集成

- `api()` 每次请求自动注入 `Authorization: Bearer <access>`。
- 401 → 尝试 refresh → 成功重放；失败 → 清 token → 跳 `/login`。
- WS 鉴权用子协议 `Sec-WebSocket-Protocol: bearer, <access>`。

## Non-goals

- 不做移动端适配（桌面优先，响应式 best-effort）。
- 不做可视化 token 消耗统计图（后续 change）。
- 不做会话重命名 / 删除（UI 占位 disabled）。
- 不做消息引用跳转（[1] 跳到 RetrievalCard 高亮）。
- 不做 Ctrl+K 命令面板（后续 change）。

## Impact

- **新增**：`web/src/features/` 下约 20 个 tsx、`web/src/lib/` 4 个 ts、`components/ui/` 5 个 tsx。
- **修改**：`web/package.json` 依赖、`router.tsx`、`providers.tsx`、`docs/openapi.json`（用于类型生成）。
- **依赖**：上面 7 个 JS 包。
- **风险**：中。SSE/WS 的流式渲染与 abort 语义是典型坑点；必须在 Change 14 之前解决得稳定。
- **回退方式**：`git revert` 本 change 即可回到 placeholder 骨架。
