# Proposal: TUI Three-Pane Layout (Sidebar + Transcript + Input)

## Why

当前 CLI 是顺序打印的"REPL"：用户看不到自己**当前在哪个 session**、有哪些 session、下一步能切什么。痛点实测：

- 启动后看到 banner，但不知道"我现在的对话挂在哪个 session 上"。
- `/sessions` 列出来就过去了，下一秒又忘了。
- 想换 ollama 模型？`/model` 是占位，没实装。
- 想注册个新账号？没有 `/register`，只能跑去 curl 或开 Web。
- session 全是 hex UUID，看不出"哪段是聊 Rust，哪段是问 memory"。

豆包 / cursor / k9s / lazygit 早就证明了：**侧边栏 + 主区 + 输入栏**这种"信息架构"在终端里完全可以做（哪怕视觉打折）。本 change 把 CLI 升级成全屏 TUI，让用户**永远看得到上下文**。

## What Changes

- **`ui/app.py`（新）**：基于 `prompt_toolkit.Application` 的全屏三栏布局：
  - 左：sessions 列表（可选中、`Tab` 切焦点、`Enter` 切会话）
  - 右上：transcript（user/asst 着色，自动锚底）
  - 右下：input box + status toolbar
- **`ui/sessions_pane.py` / `ui/transcript_pane.py` / `ui/input_pane.py`（新）**：三个 pane 各自的状态 + 渲染逻辑，纯展示层，零业务依赖。
- **`ui/commands.py`（新）**：斜杠命令分发器，加上：
  - **`/register`**（新）— 邮箱+密码注册，复用 `core.auth.service.AuthService.register`
  - **`/sessions`**（新增） — 刷新侧边栏（其实平时一直显示，但提供命令路径）
  - **`/switch <id>`**（新） — 切到指定 session（也可以在侧边栏按 ↑↓ + Enter）
  - **`/new [title]`** — 新建 session，可选传入标题
  - **`/title <text>`**（新） — 重命名当前 session（仅 DB mode）
  - **`/delete`**（新） — 删当前 session
  - **`/model`**（新实装） — 列 `OllamaClient.list_models()` 返回值
  - **`/model <name>`**（新实装） — 切到该模型，运行时生效，不持久化
  - **`/rag on|off`** / **`/think on|off`**（新） — toggle，写入 UI 状态
  - 已有 `/login /logout /whoami /clear /quit /help` 全部保留
- **`core/llm/ollama.py`**：新增 `list_models() -> list[str]`，调 `GET /api/tags`，返回模型名列表。
- **`core/memory/chat_memory.py`**：
  - `ChatMemory` Protocol 新增 `set_title(session_id, title)` —— file backend no-op，DB backend `UPDATE chat_sessions SET title=...`
  - `FileChatMemory.list_sessions()` 增强：返回 `list[SessionMeta]`（含 id + 标题 + 消息数）。`SessionMeta` 是新 dataclass。**保留旧 `list_sessions() -> list[str]` 不破坏 API**——加新方法 `list_session_metas()`，旧方法 deprecated。
  - **session 标题取第一条 user message 前 24 字**：`FileChatMemory` 在 `list_session_metas()` 里现算；`DbChatMemory` 优先用 `chat_sessions.title`，无则同样现算。
- **`app/chat_app.py`**：`run_chat()` 重写成 TUI 入口，`run_legacy_chat()` 保留旧顺序模式作为 `--legacy` flag 的 fallback（环境异常时不至于完全没法用）。
- **`app/cli.py`**：`chat` 子命令加 `--legacy` 开关；默认走 TUI。

## Non-goals

- **不做 Markdown 流式渲染**：v1 用带色普通文本（user 绿、asst 青、sys 灰）；rich 与 prompt_toolkit 全屏冲突，桥接 ANSI 留 v2。
- **不做鼠标点击切 session**：键盘已够（终端鼠标兼容性差异大）。
- **不做 LLM 智能总结标题**：v1 截 24 字够用；LLM 总结留 v2，要起后台任务。
- **不做"DB + file 双写缓存"**：登录 DB / 未登录 file，直接走；缓存留 Change 8 (`add-redis-and-workers`)。
- **不动 REST/SSE/WS 任何一行业务代码**。

## Impact

- **新增**：`ui/app.py / sessions_pane.py / transcript_pane.py / input_pane.py / commands.py`；`core/llm/ollama.py::list_models`；`core/memory/chat_memory.py::SessionMeta + list_session_metas + set_title`。
- **修改**：`app/chat_app.py`（重写 `run_chat`）、`app/cli.py`（加 `--legacy`）、`ui/__init__.py`（导出 `run_tui_chat`）。
- **依赖**：无新增（`prompt_toolkit>=3.0.43` 已在）。
- **风险**：中。
  - prompt_toolkit Application 全屏接管和现有 `rich.live.Live` 二选一；本 change 选 prompt_toolkit，旧 `ui/chat_view.py` 留给 `--legacy` 用，不删。
  - 测试会变难：全屏 TUI 不能 `subprocess.run` 断言 stdout，只能单元测 pane / commands 的纯函数 + 一条 `--legacy` smoke。
- **回退**：`git revert`，或运行时 `python main.py chat --legacy`。
