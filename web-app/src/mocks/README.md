# MSW Mock

Demo 账号：

- email: `demo@rag-chat.local`
- password: `demo1234`

启用方式：`.env` 里 `VITE_USE_MOCK=true`（默认已开）。

首次运行前，请在 `web-app/` 目录执行一次：

```bash
pnpm dlx msw init public/ --save
```

它会把 `mockServiceWorker.js` 放到 `public/`（该文件不需要人工编辑）。
