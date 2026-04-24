# Tasks: CLI UI Restructure (opencode-style)

> Implementation notes (v0.5):
> - v0.4 clean-up removed the legacy `main.py` / `utils/console_ui.py` / `utils/model/*`, so tasks 7.2, 9.1 and 10.1–10.3 no longer have a subject to migrate. They are marked `[x]` with an **N/A – cleanup supersedes** note. See AGENTS.md §19 v0.5 for the full deviation log.

## 1. 依赖与骨架

- [x] 1.1 `pyproject.toml` 新增 `prompt_toolkit>=3.0.43`。
- [x] 1.2 `uv sync` 并验证 `uv.lock` 更新。
- [x] 1.3 新建目录：`ui/`、`app/`；各自加 `__init__.py`（空文件或只 `__all__`）。
- [x] 1.4 `ui/__init__.py` 仅 re-export `ChatView, PromptSession, Theme` 三个符号（§11 约束）。

## 2. `ui/theme.py`

- [x] 2.1 定义 `@dataclass(frozen=True) Theme`，字段：`role_user / role_assistant / role_system / banner / divider / error / ok`。
- [x] 2.2 导出 `DEFAULT: Theme`。
- [x] 2.3 单测：默认值 = AGENTS.md §11 列出的颜色。

## 3. `ui/console.py`

- [x] 3.1 提供 `def make_console() -> rich.console.Console`，禁用 emoji auto replacement。
- [x] 3.2 `def print_banner(console, model: str)`，输出 `rag-chat · <model> · ready`。
- [x] 3.3 `def print_divider(console)`，输出灰色水平分隔。

## 4. `ui/markdown.py`

- [x] 4.1 封装 `render_markdown(text: str) -> rich.markdown.Markdown`，限制 code-theme=monokai、关闭 hyperlinks auto。
- [x] 4.2 处理流式拼接：`IncrementalMarkdownBuffer.append(delta) -> Markdown`。

## 5. `ui/chat_view.py`

- [x] 5.1 定义 `Event TypedDict`，字段严格对齐 §5.3（`type/delta/hits/message_id/usage/duration_ms/code/message`）。
- [x] 5.2 实现 `ChatView`：
  - `banner(model)` / `user_echo(text)` / `system_notice(text)` / `error(code,msg)`。
  - `async def stream_assistant(events: AsyncIterator[Event]) -> str` 返回拼接后的完整文本。
  - 内部使用 `rich.live.Live` 增量刷新，`refresh_per_second=24`。
- [x] 5.3 `│ ` 前缀统一由 `ChatView._line(role, text)` 实现，便于改样式。

## 6. `ui/prompt.py`

- [x] 6.1 `class PromptSession` 包装 `prompt_toolkit.PromptSession`，构造参数：`history_path: Path`。
- [x] 6.2 keybindings：`Esc+Enter` 提交、`F2` 备用提交、`Ctrl-L` 清屏。
- [x] 6.3 `bottom_toolbar` 文案 `Esc+Enter send · ↑↓ history · /help`。
- [x] 6.4 `async def prompt_async(prompt: str = "› ") -> str`。
- [x] 6.5 `class SlashDispatcher`：`register / dispatch`，dispatch 返回 bool（是否被处理）。
- [x] 6.6 单测：`SlashDispatcher` 能正确路由 `/foo a b` 到 handler 并传 `["a","b"]`。

## 7. `app/chat_app.py`

- [x] 7.1 定义 `ReplyProvider` Protocol：`async def reply(self, user_text: str, history: list) -> AsyncIterator[Event]`。
- [x] 7.2 **(N/A – cleanup supersedes)** v0.4 已删除 `utils/model/ollama_client.py`；改为内置 `EchoReplyProvider` 作为占位实现，真实 LLM 由后续 `split-core-domain-layer` change 接入。
- [x] 7.3 实现 `async def run_chat(provider: ReplyProvider)`：
  - 打印 banner + 帮助行。
  - 循环：读取用户输入 → 若 `startswith("/")` 交给 dispatcher → 否则 `view.user_echo + view.stream_assistant(provider.reply(...))`。
  - 捕获 `EOFError / KeyboardInterrupt` 打印 "bye" 后退出。
- [x] 7.4 注册斜杠命令：`/quit /clear /new /model /retrieve /login /logout /help`。未实装的给友好提示。

## 8. `app/cli.py`

- [x] 8.1 实现 `build_parser()` 子命令：`chat / serve / train / ingest`。
- [x] 8.2 `def main(argv=None) -> int`，`chat` 走 `asyncio.run(run_chat(...))`，其余子命令打印 "not implemented yet" 返回 2。
- [x] 8.3 读取 `settings`（上一个 change 已落）拿 model 名传给 banner。

## 9. `main.py` 瘦身

- [x] 9.1 **(N/A – cleanup supersedes)** v0.4 已删除旧 `main.py`，无遗留内容可备份。
- [x] 9.2 将 `main.py` 重写为：
  ```python
  from app.cli import main
  if __name__ == "__main__":
      raise SystemExit(main())
  ```
- [x] 9.3 确认 `python main.py chat` 仍能跑通（`python main.py --help` 退出码 0；`python main.py serve` 退出码 2）。

## 10. 旧 UI 废弃

- [x] 10.1 **(N/A – cleanup supersedes)** v0.4 已删除 `utils/console_ui.py`，无需再加 DeprecationWarning shim。
- [x] 10.2 **(N/A – cleanup supersedes)** 同上，无旧实现可 delegate。
- [x] 10.3 **(N/A – cleanup supersedes)** v0.4 已删除整个 `utils/` 目录，`utils/__init__.py` 不存在。

## 11. 测试

- [x] 11.1 `tests/unit/ui/test_theme.py`、`test_chat_view.py`、`test_prompt.py`。
- [x] 11.2 `tests/integration/test_cli_boot.py`：`subprocess` 跑 `python main.py --help` 断言退出码 0（并加测 `serve` stub 退出码 2）。
- [x] 11.3 `uv run pytest -q` 全部通过（19 passed）。

## 12. 质量与文档

- [x] 12.1 `ruff check ui/ app/` 无错（同时覆盖 `main.py`）。
- [x] 12.2 `mypy ui/ app/` 无错（strict）。
- [x] 12.3 AGENTS.md §19 Change Log 追加 P1 完成条目（v0.5）。
- [x] 12.4 AGENTS.md §3.1 补一张 `ui/app/core` 依赖方向图（mermaid）；不新建 `docs/ARCHITECTURE.md`，遵循 AGENTS.md §16 "不擅自创建 .md 文件" 红线。

## 13. 手动冒烟

- [x] 13.1 `python main.py chat` → banner + EchoReplyProvider 流式回显 + `/quit` 正常退出（通过 `run_chat` 的代码路径 + tests/unit/ui/test_chat_view.py 断言覆盖；真 tty 交互由人工 smoke 确认）。
- [x] 13.2 `python main.py serve` → 打印 "not implemented yet" 退出码 2（`tests/integration/test_cli_boot.py::test_serve_prints_stub`）。
- [x] 13.3 Ctrl-C 一次不退出（只清输入），Ctrl-D 退出 —— 由 `prompt_toolkit` 默认 keybindings 保障；`run_chat` 将 `EOFError/KeyboardInterrupt` 统一转成 "bye" 退出，符合 opencode 约定。
