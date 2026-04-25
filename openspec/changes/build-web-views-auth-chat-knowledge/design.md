# Design: Web Views (Auth / Chat / Knowledge)

## Context

Change 7 已经定下 `StreamEvent` 四种类型，Change 6 定下所有 REST schema，Change 12 搭好骨架 + Tailwind。本 change 的设计重心：

1. **State 切分**：react-query 管 server state；zustand 管 session-scoped UI state（token、当前 session id、theme）。
2. **流式渲染**：WS 优先、SSE 回退、Abort 一致语义。
3. **类型安全**：从 `docs/openapi.json` 生成 TypeScript 类型，前后端契约同步。

## Goals / Non-Goals

**Goals**
- **对齐 CLI**：视觉与交互尽量与 opencode-style CLI 一致（同主题色、同 retrieval 卡片样式、同 `[n]` 引用）。
- **无 any**：生成类型 + 自定义业务类型覆盖所有网络边界。
- **稳健流式**：断网 / 后端 500 / abort 三种场景都有明确 UI 反馈。
- **可访问性**：`form` 元素必须有 `label`、按钮必须有 `aria-label`、键盘可达。

**Non-Goals**
- 不做全量 a11y 审计（只做基础）。
- 不做消息虚拟滚动（后续 change）。

## Architecture

### Providers 链

```tsx
// app/providers.tsx
<QueryClientProvider client={qc}>
  <ThemeProvider>
    <AuthBootstrapper>
      {children}
    </AuthBootstrapper>
    <Toaster richColors closeButton />
  </ThemeProvider>
</QueryClientProvider>
```

`AuthBootstrapper`：mount 时调 `useAuthTokenBootstrap()`，loading 期间给一个全屏 Spinner。

### AuthStore（zustand，持久化到 localStorage）

```ts
interface AuthState {
  access: string | null;
  refresh: string | null;
  user: UserOut | null;
  setTokens(p: TokenPair): void;
  setUser(u: UserOut | null): void;
  clear(): void;
}
export const useAuth = create<AuthState>()(persist(
  (set) => ({
    access: null, refresh: null, user: null,
    setTokens: (p) => set({ access: p.access_token, refresh: p.refresh_token }),
    setUser: (user) => set({ user }),
    clear: () => set({ access: null, refresh: null, user: null }),
  }),
  { name: "ragchat-auth", partialize: (s) => ({ access: s.access, refresh: s.refresh }) },
));
```

### API client

`lib/api.ts` 扩展：

```ts
let refreshPromise: Promise<void> | null = null;

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { access } = useAuth.getState();
  const headers = new Headers(init.headers);
  headers.set("content-type", "application/json");
  if (access) headers.set("authorization", `Bearer ${access}`);

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    await ensureRefresh();   // single-flight
    return api<T>(path, init);  // retry once
  }
  if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => ({})));
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

async function ensureRefresh() {
  if (!refreshPromise) refreshPromise = doRefresh().finally(() => (refreshPromise = null));
  await refreshPromise;
}
```

### openapi-typescript 集成

- 脚本 `web/scripts/gen-types.ts` 或直接 `pnpm run gen:types` → `openapi-typescript ../docs/openapi.json -o src/lib/api.gen.ts`。
- `package.json` script：`"gen:types": "openapi-typescript ../docs/openapi.json -o src/lib/api.gen.ts"`。
- `web/src/lib/types.ts` re-export 关键类型，`api.ts` 只依赖 `types.ts`，保证生成文件变更隔离。

### 路由

```tsx
// router.tsx
createBrowserRouter([
  { path: "/login", element: <LoginPage/> },
  { path: "/register", element: <RegisterPage/> },
  {
    element: <ProtectedRoute />,
    children: [
      { path: "/", loader: () => redirect("/chat") },
      { path: "/chat", element: <ChatLayout /> },
      { path: "/chat/:sessionId", element: <ChatLayout /> },
      { path: "/knowledge", element: <KnowledgePage /> },
    ],
  },
  { path: "*", element: <NotFound /> },
]);
```

`ProtectedRoute`：未登录 → `<Navigate to="/login" replace/>`。

### Chat 数据流

```
SessionSidebar ─── useQuery(["sessions"], listSessions)
       │
       ▼ onSelect(sid) → useAuth.setCurrentSession(sid)
MessageList ─── useQuery(["messages", sid], listMessages)
       │
ChatInput.onSubmit → useChatStream().send({content, use_rag})
       │
useChatStream ──► WebSocket (优先) / SSE (回退)
       │  ▲
       │  └── 事件流回调：retrieval → push RetrievalCard；token → setDraft; done → invalidate(["messages",sid]); error → toast.error
       ▼
StreamingMessage 组件订阅 draft state，逐字渲染
```

### `useChatStream.ts`

```ts
export function useChatStream(sessionId: string) {
  const [hits, setHits] = useState<RetrievalHit[]>([]);
  const [draft, setDraft] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  async function send(body: { content: string; use_rag: boolean }) {
    setHits([]); setDraft("");
    const ac = new AbortController(); abortRef.current = ac;
    const mode = import.meta.env.VITE_STREAM ?? "ws";
    if (mode === "ws") return runWs(sessionId, body, { onHits: setHits, onToken: (d) => setDraft((x) => x + d) });
    return runSse(sessionId, body, { signal: ac.signal, onHits: setHits, onToken: (d) => setDraft((x) => x + d) });
  }

  function abort() { abortRef.current?.abort(); wsRef.current?.send(JSON.stringify({ type: "abort" })); }

  return { hits, draft, send, abort, isStreaming: draft.length > 0 /* or explicit flag */ };
}
```

### `lib/ws.ts` 关键

```ts
export async function runWs(
  sessionId: string,
  payload: { content: string; use_rag: boolean },
  cbs: { onHits: (h: RetrievalHit[]) => void; onToken: (d: string) => void }
) {
  const { access } = useAuth.getState();
  const ws = new WebSocket(
    `${wsBase()}/ws/chat`,
    ["bearer", access!]   // 子协议鉴权
  );
  // onopen → send {type:"user_message", session_id, content, use_rag}
  // onmessage → 判别 type 调回调；done → ws.close()
  // onerror / onclose → reject or resolve
}
```

### Chat 视觉

- 左栏 280px，右栏 flex-1。
- 消息气泡：user 右对齐、`bg-accent/10`；assistant 左对齐、无背景；system 消息灰色小字。
- `RetrievalCard`：assistant 气泡上方，Collapsible（折叠态只显示 "📎 引用 3 处"）。
- `ChatInput`：`<textarea>` 自动撑高（最多 8 行），`Enter` 发送，`Shift+Enter` 换行；右下角 RAG toggle（开关）+ 中断按钮（流式中可见）。

### Knowledge 视觉

- `KnowledgePage` 单列布局：顶部 SearchBar + ReindexButton + UploadDropzone，下方 DocumentList。
- 上传拖拽区最多接受 10MB；超限 toast 报错；文本文件读取 `FileReader.readAsText` → `POST /knowledge/documents`。
- SearchBar 结果以 Card 列表展示，点击 hit 暂不跳转（后续接文档详情页）。

## Alternatives Considered

- **Redux Toolkit**：过重；zustand + react-query 已足够。
- **graphql-codegen**：后端是 REST，不适配。
- **eventsource polyfill**：现代浏览器 SSE 原生支持够用；优先 WS + fetch-SSE fallback。

## Risks & Mitigations

- **风险**：WS 鉴权子协议在某些代理（Nginx 默认）会被丢弃。
  **缓解**：同时支持 `?token=...` query fallback；Change 10 的 nginx 已开 `proxy_pass_header Sec-WebSocket-Protocol`。
- **风险**：流式渲染频繁 setState 引起性能抖动。
  **缓解**：`draft` 使用 `useRef + flush via rAF`，减少 React re-render。
- **风险**：401 refresh 与另一个请求并发时重放爆炸。
  **缓解**：`ensureRefresh` 是 single-flight 模式。
- **风险**：Markdown 渲染被注入 script。
  **缓解**：`react-markdown` 默认不执行 HTML；确保 `rehype-raw` **不启用**；对 `<a>` 加 `rel="noopener noreferrer"`。

## Testing Strategy

- 单元（vitest，本 change 也引入）：
  - `useChatStream` 使用 mocked WebSocket 验证事件回调顺序。
  - `lib/api.ts` 401 → refresh → retry 路径。
- 端到端（playwright 可选，暂不强求，本 change 不接入）。
- 手动验收清单（`docs/WEB_QA.md`）：
  - 登录失败错误提示；注册成功跳 /chat。
  - 新建 session → 发送消息 → 看到 retrieval card + 流式 token + 结尾 usage。
  - 中断流式后再发一条消息仍正常。
  - 上传 md 文件 → reindex → search 命中。
  - 主题切换 / 刷新保持。
