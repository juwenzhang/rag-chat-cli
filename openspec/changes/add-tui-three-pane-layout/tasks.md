# Tasks: add-tui-three-pane-layout

## 1. Memory layer
- 1.1 `core/memory/chat_memory.py` 新增 `SessionMeta` dataclass。
- 1.2 `ChatMemory` Protocol 加 `list_session_metas()` + `set_title()`.
- 1.3 `FileChatMemory.list_session_metas()` —— 读首条 user msg 取前 24 字。
- 1.4 `FileChatMemory.set_title()` —— no-op (warn-once log)。
- 1.5 `DbChatMemory.list_session_metas()` —— ORM 拉 sessions + 首条 user msg。
- 1.6 `DbChatMemory.set_title()` —— UPDATE with user_id check。

## 2. LLM enhancement
- 2.1 `core/llm/ollama.py::list_models()`。
- 2.2 `core/chat_service.py::generate(model=None)` 透传到 `chat_stream`。

## 3. UI primitives
- 3.1 `ui/state.py`：`TuiState` dataclass。
- 3.2 `ui/transcript.py`：`TranscriptBuffer` 类（deque-backed，cap 1000）+ render hook。
- 3.3 `ui/sessions_pane.py`：`SessionsPaneControl(FormattedTextControl)`，cursor 高亮渲染。
- 3.4 `ui/transcript_pane.py`：`TranscriptPaneControl`，从 buffer 拉 lines。
- 3.5 `ui/status_bar.py`：单行状态栏。

## 4. Application
- 4.1 `ui/app.py`：`build_application(state, on_send, on_command)`。
- 4.2 keybindings：Esc+Enter / Tab / Ctrl+B/N/D/L/Q + sidebar 上下/Enter。
- 4.3 layout：HSplit + VSplit + ConditionalContainer。

## 5. Commands
- 5.1 `ui/commands.py::SlashDispatcher` 重构（搬现有 + 加新）。
- 5.2 实装 `/register` `/sessions` `/switch` `/new [title]` `/title <text>` `/delete` `/model [name]` `/rag on|off` `/think on|off`。
- 5.3 保留 `/login /logout /whoami /help /clear /quit`。

## 6. Wire to provider
- 6.1 `ChatServiceProvider` 加 `_model` 字段 + 透传给 `service.generate(model=...)`。
- 6.2 `app/chat_app.py::run_tui_chat()` 新版本。
- 6.3 旧 `run_chat` 改名 `run_legacy_chat`。

## 7. CLI
- 7.1 `app/cli.py::chat` 子命令加 `--legacy`。
- 7.2 默认走 TUI；`--legacy` 走旧顺序模式。

## 8. Tests
- 8.1 `tests/unit/ui/test_transcript_buffer.py`（4 条）。
- 8.2 `tests/unit/ui/test_sessions_pane_render.py`（2 条）。
- 8.3 `tests/unit/core/test_session_meta.py`（1 条 file backend）。
- 8.4 修 `tests/integration/test_cli_boot.py`：`test_main_help_exits_zero` 不变；新增 `test_chat_legacy_mode_quits` 用 `--legacy` 走旧路径。

## 9. Quality gates
- 9.1 `uv run ruff check .`
- 9.2 `uv run ruff format --check .`
- 9.3 `uv run mypy --strict . --explicit-package-bases`
- 9.4 `uv run pytest -q`
- 9.5 `make ci`

## 10. Smoke
- 10.1 `python main.py chat --legacy` → 旧体验，`/quit` 干净退出。
- 10.2 `python main.py chat`（默认 TUI）→ 看到三栏；按 `Esc Enter` 发一句；按 `Ctrl+B` 折叠 sidebar；按 `Ctrl+Q` 退出。
- 10.3 `/model` 列出已有模型；`/model qwen2.5:1.5b` 切换；下一句 chat 用新模型（看 ollama log 确认）。
- 10.4 `/register` 走完三步输入 → DB users 表多一行。

## 11. Docs
- 11.1 AGENTS.md §11 增补 TUI 段；§19 加 v1.3 条目。
