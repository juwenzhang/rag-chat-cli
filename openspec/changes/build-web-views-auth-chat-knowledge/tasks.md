# Tasks: Web Views (Auth / Chat / Knowledge)

## 1. 依赖

- [ ] 1.1 `cd web && pnpm add @tanstack/react-query zustand react-hook-form zod @hookform/resolvers react-markdown remark-gfm rehype-highlight lucide-react sonner`。
- [ ] 1.2 dev：`pnpm add -D vitest @testing-library/react @testing-library/jest-dom jsdom openapi-typescript`。
- [ ] 1.3 `pnpm install --frozen-lockfile` 绿。

## 2. 类型生成

- [ ] 2.1 根目录 `make openapi` 确保 `docs/openapi.json` 最新。
- [ ] 2.2 `web/package.json` 添加 `"gen:types": "openapi-typescript ../docs/openapi.json -o src/lib/api.gen.ts"`。
- [ ] 2.3 跑 `pnpm gen:types` 生成 `src/lib/api.gen.ts`。
- [ ] 2.4 `src/lib/types.ts` re-export：`User`、`ChatSession`、`Message`、`Document`、`SearchHit`、`TokenPair` 等。

## 3. Providers

- [ ] 3.1 `app/providers.tsx` 注入 `QueryClientProvider`（QueryClient 设 staleTime 30s、retry false 针对 4xx）。
- [ ] 3.2 `ThemeProvider`：从 `localStorage` 初始化 `data-theme`；暴露 hook `useTheme()`。
- [ ] 3.3 `AuthBootstrapper`：mount 时跑 `useAuthTokenBootstrap`；loading 全屏 Spinner。
- [ ] 3.4 `<Toaster richColors closeButton position="top-center" />`。

## 4. AuthStore

- [ ] 4.1 `features/auth/AuthStore.ts`：zustand + persist（按 design）。
- [ ] 4.2 `useAuthTokenBootstrap.ts`：有 access → `GET /me`；401 → 尝试 refresh；失败 clear + redirect。
- [ ] 4.3 登录/登出 mutation 封装：`useLogin()`、`useLogout()`（react-query useMutation）。

## 5. Auth 视图

- [ ] 5.1 `LoginPage.tsx`：`react-hook-form` + `zodResolver`，字段 email、password（min 8）。
- [ ] 5.2 错误展示：401 显示 "邮箱或密码错误"，其它显示 toast。
- [ ] 5.3 登录成功 → `navigate("/chat")`。
- [ ] 5.4 `RegisterPage.tsx`：多一个 `display_name` 可选字段；注册成功自动登录并跳 `/chat`。
- [ ] 5.5 `ProtectedRoute.tsx`：见 design，loading 时返回 Spinner。
- [ ] 5.6 UI：卡片居中，宽 400px，含 logo、主题切换按钮。

## 6. API client 扩展

- [ ] 6.1 `lib/api.ts` 增强：注入 Authorization；401 走 ensureRefresh（single-flight）。
- [ ] 6.2 单测：mock fetch，验证 401 → refresh → retry 路径；refresh 失败清 auth 并抛 `ApiError(401)`。

## 7. SSE / WS 客户端

- [ ] 7.1 `lib/sse.ts`：`async function runSse(...)` 使用 `fetch(..., { method: "POST", signal })` 并读 `res.body` 的 `ReadableStream`，按 SSE 格式切分事件。
- [ ] 7.2 `lib/ws.ts`：`runWs(...)` 按 design；鉴权子协议 + query 双路径。
- [ ] 7.3 事件解析封装 `parseStreamEvent(raw): StreamEvent` 含 `type` 判别。
- [ ] 7.4 测试：Node 下用 `ws` 包起个假服务器，模拟 4 种事件序列，断言回调顺序。

## 8. Chat 视图

### 8.1 `ChatLayout.tsx`
- [ ] 8.1.1 左右 flex 布局；响应式 `md:` 断点以下改为抽屉式 Sidebar。

### 8.2 `SessionSidebar.tsx`
- [ ] 8.2.1 `useQuery(["sessions"], listSessions, { refetchOnWindowFocus: true })`。
- [ ] 8.2.2 顶部 "＋ 新建" 按钮调 `POST /chat/sessions`，成功后 `navigate(/chat/:id)`。
- [ ] 8.2.3 当前 session 高亮；hover 出现（暂 disabled）的 ✎ ⌫ 按钮。

### 8.3 `MessageList.tsx`
- [ ] 8.3.1 `useQuery(["messages", sid], {enabled: !!sid})`，分页 size=50。
- [ ] 8.3.2 列表末尾追加 `<StreamingMessage>`（仅流式中可见）。
- [ ] 8.3.3 自动滚动到底（`useEffect` 监听 draft / messages）。

### 8.4 `MessageBubble.tsx`
- [ ] 8.4.1 `role=user`：右对齐，`bg-accent/10 rounded px-3 py-2`。
- [ ] 8.4.2 `role=assistant`：左对齐，使用 `<ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>`。
- [ ] 8.4.3 `role=system`：居中灰色小字。
- [ ] 8.4.4 Markdown code block 显示"复制"按钮。

### 8.5 `RetrievalCard.tsx`
- [ ] 8.5.1 折叠 / 展开：默认折叠显示 "📎 引用 N 条"。
- [ ] 8.5.2 展开后列出 `[1] title — snippet…`，鼠标悬浮显示分数。
- [ ] 8.5.3 点击复制 snippet 到剪贴板 + toast。

### 8.6 `StreamingMessage.tsx`
- [ ] 8.6.1 订阅 `useChatStream` 的 draft；有内容才渲染。
- [ ] 8.6.2 底部显示一个"闪烁光标"字符。
- [ ] 8.6.3 流式中在右下显示"中断"按钮 → 调 `abort()`。

### 8.7 `ChatInput.tsx`
- [ ] 8.7.1 `<textarea>` 使用 `react-textarea-autosize`（可直接 `rows` 伸缩脚本，不加新 dep）。
- [ ] 8.7.2 `Enter` 发送，`Shift+Enter` 换行；发送中禁用。
- [ ] 8.7.3 `RAG` 开关（Switch 组件），持久化到 zustand。
- [ ] 8.7.4 发送成功：optimistic 往 messages 里 append user 消息；等 `done` 事件后 invalidate query。

### 8.8 `useChatStream.ts`
- [ ] 8.8.1 按 design 实现；暴露 `{ send, abort, draft, hits, isStreaming, error }`。
- [ ] 8.8.2 `error` 状态让 UI 展示红色横条 + 重试按钮。

## 9. Knowledge 视图

### 9.1 `KnowledgePage.tsx`
- [ ] 9.1.1 顶部：SearchBar（flex-1） + ReindexButton + UploadDropzone 触发按钮。
- [ ] 9.1.2 下方：TabList `我的文档 / 搜索结果`。

### 9.2 `DocumentList.tsx`
- [ ] 9.2.1 `useQuery(["documents"], listDocuments)` 分页。
- [ ] 9.2.2 每行：title、source、created_at、chunks（来自 `meta.ingest_stats.chunks`）、状态 badge（ingested/pending/failed）。

### 9.3 `UploadDropzone.tsx`
- [ ] 9.3.1 原生 drag-and-drop；支持多文件。
- [ ] 9.3.2 校验 `text/markdown | text/plain`、size ≤ 10MB；否则 toast。
- [ ] 9.3.3 提交：每文件 `FileReader → POST /knowledge/documents`；成功后 invalidate `["documents"]`。

### 9.4 `SearchBar.tsx`
- [ ] 9.4.1 `useDebouncedValue(300ms)`；`useQuery(["kb.search", q], {enabled: q.length >= 2})`。
- [ ] 9.4.2 结果 Card 列表：title + snippet + score（进度条可视化）。

### 9.5 `ReindexButton.tsx`
- [ ] 9.5.1 点击调 `POST /knowledge/documents:reindex`，成功 toast "入队 N 个任务"；失败 toast 错误。
- [ ] 9.5.2 5 秒内 disabled（防抖）。

## 10. UI 基础补全

- [ ] 10.1 `components/ui/textarea.tsx`、`avatar.tsx`、`dialog.tsx`（用 `<dialog>` 原生或自写简单 Portal）、`tabs.tsx`、`tooltip.tsx`。
- [ ] 10.2 `components/ui/switch.tsx` 用于 RAG toggle。
- [ ] 10.3 `components/ui/badge.tsx`。

## 11. 测试

- [ ] 11.1 `vitest.config.ts`：`environment: "jsdom"`。
- [ ] 11.2 `src/__tests__/api.test.ts`：401 → refresh → retry。
- [ ] 11.3 `src/__tests__/useChatStream.test.ts`：mock WS → 验证事件 → abort。
- [ ] 11.4 `src/__tests__/LoginPage.test.tsx`：表单校验、错误渲染。
- [ ] 11.5 `pnpm test` 全绿；覆盖率报告（非强制阈值，目标 > 60%）。

## 12. CI 扩展

- [ ] 12.1 `.github/workflows/ci.yml` 的 `web` job 追加 `pnpm test -- --run`。
- [ ] 12.2 依赖缓存：`actions/setup-node@v4` + `cache: pnpm`。

## 13. 文档

- [ ] 13.1 `docs/WEB_QA.md`：手动验收清单（见 design 尾部）。
- [ ] 13.2 `README.md` 更新截图占位（先放 placeholder.png）。
- [ ] 13.3 AGENTS.md §19 追加 "Web views: auth/chat/knowledge"。

## 14. 冒烟

- [ ] 14.1 `docker compose --profile full up -d --build` + `python main.py ingest AGENTS.md`。
- [ ] 14.2 浏览器 `http://localhost/`：
  - 注册 → 登录 → 创建 session → 开启 RAG → 发"what is opencode UX?" → 看到 retrieval card + 流式 token + usage。
  - 中途点"中断"按钮，流停止，UI 无异常。
  - `/knowledge` 拖上传一个 md 文件 → 状态变 ingested → 搜索命中。
- [ ] 14.3 `pnpm test` / `pnpm typecheck` / `pnpm lint` / `pnpm build` 全绿。
