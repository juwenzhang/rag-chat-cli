# Design: TUI Three-Pane Layout

## 1. Layout

```
┌─sessions ────────┬─transcript ──────────────────────────────────┐
│▸ 你好呀的对话    6│ session: 你好呀的对话 · qwen2.5:1.5b · file  │
│  Rust 进阶知识总…2│ ────────────────────────────────────────────  │
│  如何验证 memory…0│ │ you · 你好呀                                │
│                   │ │ asst · 你好！很高兴见到你...                │
│                   │ │ ...                                         │
│ Ctrl+N new        │ │                                             │
│ Ctrl+D delete     │ │                                             │
├───────────────────┴──────────────────────────────────────────────│
│ › 输入消息，Esc+Enter 发送                                        │
│ model:qwen2.5:1.5b · rag:off · think:off · Tab=switch · /help    │
└──────────────────────────────────────────────────────────────────┘
```

宽度自适应：sidebar 固定 24 字符，input 固定 5 行，transcript 占剩余空间。

## 2. State container

```python
# ui/state.py
@dataclass
class TuiState:
    # data
    sessions: list[SessionMeta]
    current_session_id: str | None

    # ui flags
    focused_pane: Literal["sidebar", "input"] = "input"
    sidebar_visible: bool = True
    sidebar_cursor: int = 0   # index into sessions

    # runtime config
    current_model: str
    available_models: list[str]
    rag_enabled: bool = False
    think_enabled: bool = False

    # auth shadow
    user_email: str | None = None    # populated after /login
    memory_mode: Literal["file", "db", "file (db-unavailable)"] = "file"
```

State 是单例，pane 渲染只读 state，事件回调写 state 后调 `Application.invalidate()` 触发重画。

## 3. Application skeleton

```python
# ui/app.py
def build_application(state: TuiState, on_send: Callable[[str], Awaitable[None]],
                      on_command: Callable[[str], Awaitable[None]]) -> Application:
    sidebar = SessionsPaneControl(state)
    transcript = TranscriptPaneControl(state)
    input_box = TextArea(multiline=True, height=Dimension(preferred=5, min=3, max=10),
                         prompt="› ", wrap_lines=True)
    toolbar = StatusBarControl(state)

    layout = Layout(HSplit([
        VSplit([
            ConditionalContainer(
                Window(sidebar, width=Dimension.exact(24), wrap_lines=False),
                filter=Condition(lambda: state.sidebar_visible),
            ),
            Window(char="│", width=1),
            Window(transcript, wrap_lines=True),
        ]),
        Window(char="─", height=1),
        input_box,
        Window(toolbar, height=1),
    ]))

    kb = build_keybindings(state, input_box, on_send, on_command)
    return Application(layout=layout, key_bindings=kb, full_screen=True, mouse_support=False)
```

## 4. Keybindings

| 键 | filter | 动作 |
|---|---|---|
| `Esc Enter` | input focused | submit input box content |
| `Ctrl+B` | always | toggle sidebar visibility |
| `Tab` | always | rotate focus sidebar ↔ input |
| `Ctrl+N` | always | `_cmd_new(state)` |
| `Ctrl+D` | sidebar focused | `_cmd_delete_current(state)` |
| `↑` / `↓` | sidebar focused | move `sidebar_cursor` |
| `Enter` | sidebar focused | switch to `state.sessions[sidebar_cursor]` |
| `Ctrl+L` | always | clear transcript pane |
| `Ctrl+Q` | always | `app.exit()` |
| `Ctrl+C` | always | (v1) `app.exit()`；v2 abort 当前 stream |

## 5. Commands

`ui/commands.py` 的 `SlashDispatcher` 接受 `(state, services)` 上下文，每个命令是 `async (args: list[str]) -> None`。services 是依赖注入的容器：

```python
@dataclass
class TuiServices:
    provider: ReplyProvider           # for /model switch (provider holds model)
    auth_service_factory: Callable[[], AuthService]  # lazy DB init
    memory: ChatMemory                # for sessions / titles
    ollama: OllamaClient              # for list_models
    transcript: TranscriptBuffer      # for printing system messages
```

命令实现都是**纯协程**，不直接 touch prompt_toolkit Application —— 写 state，invalidate 由调用方触发。

## 6. Memory enhancements

```python
# core/memory/chat_memory.py
@dataclass(frozen=True, slots=True)
class SessionMeta:
    id: str
    title: str            # 24-char preview or DB-stored title
    message_count: int
    updated_at: datetime | None  # None for file backend without mtime ordering


class ChatMemory(Protocol):
    # ... existing methods ...
    async def list_session_metas(self) -> list[SessionMeta]: ...
    async def set_title(self, session_id: str, title: str) -> None: ...
```

* `FileChatMemory.list_session_metas()` 现算 title：读每个 JSON 第一条 `role=user` 的 content，取前 24 字（unicode 字符不是字节）。
* `FileChatMemory.set_title()` —— **no-op**（file 不存 title），方法存在保 Protocol 完整。
* `DbChatMemory.list_session_metas()` —— SQL 拉 sessions + count 子查询；`title` `COALESCE(chat_sessions.title, '<first user msg substring>')`。先用 ORM 拉 sessions，再对每个 session 拉首条 user msg —— N+1 但**典型用户 < 50 sessions**，可接受。
* `DbChatMemory.set_title()` —— `UPDATE chat_sessions SET title = ? WHERE id = ? AND user_id = ?`。

## 7. OllamaClient.list_models

```python
async def list_models(self) -> list[str]:
    """GET /api/tags → list of model names. Empty list on transport error."""
    client = self._ensure_client()
    try:
        resp = await client.get("/api/tags", timeout=5.0)
    except httpx.HTTPError:
        return []
    if resp.status_code >= 400:
        return []
    data = resp.json()
    models = data.get("models") or []
    return [m["name"] for m in models if isinstance(m, dict) and "name" in m]
```

启动时调一次：
- 如果 `settings.ollama.chat_model` 在列表里 → `current_model = settings.ollama.chat_model`
- 否则取列表第一个 + 在 transcript 打 system 提示
- 列表为空 → 保持 settings 值 + 在 transcript 提示 "no models pulled, /model unavailable"

## 8. Render details

**Sidebar 行渲染** (`SessionsPaneControl.create_content`)：
```
▸ 你好呀的对话              6  ← cursor 行高亮 + reverse video
  Rust 进阶知识总结一下…    2
  如何验证 memory 生效了…   0
```
- 当前 session 前缀 `▸`
- title 截 18 字 + `…`
- message_count 右对齐 3 字符

**Transcript 行渲染**：
- `you · <text>` 绿
- `asst · <text>` 青
- `sys · <text>` 灰
- 流式时，asst 行不立即创建——先打 `asst · ` 前缀，每个 token append 到同一行（用 `transcript.append_to_last(delta)`）；done 时换行 + 加分隔
- 所有行存进 `TranscriptBuffer` 的 deque（cap 1000 行避免内存爆）

**Status bar**：单行：`model:<m> · rag:<on|off> · think:<on|off> · mem:<file|db> · /help`，根据 state 即时更新。

## 9. Streaming integration

`ChatServiceProvider.reply(line, history) -> AsyncIterator[Event]` 已经返回 events。TUI 主循环：

```python
async def _on_send(text: str) -> None:
    if text.startswith("/"):
        await dispatcher.dispatch(text)
        app.invalidate()
        return
    state.transcript.add_user(text)
    state.transcript.start_assistant()
    async for evt in services.provider.reply(text, []):
        if evt["type"] == "token":
            state.transcript.append_to_assistant(evt["delta"])
        elif evt["type"] == "done":
            state.transcript.end_assistant(duration_ms=evt.get("duration_ms"))
        elif evt["type"] == "error":
            state.transcript.add_error(evt.get("code"), evt.get("message"))
        elif evt["type"] == "retrieval":
            hits = evt.get("hits") or []
            state.transcript.add_system(f"retrieved {len(hits)} chunk(s)")
        app.invalidate()
    # Refresh sidebar (message count / new session might have appeared).
    state.sessions = await services.memory.list_session_metas()
```

`app.invalidate()` 是 prompt_toolkit 的"请求重画"，cheap，每个 token 调一次都没问题（pt 内部自带节流到 ~24fps）。

## 10. Model switch wiring

`ChatServiceProvider` 持有 `_use_rag` 和 `_session_id`，**不**持有 model。让它接受运行时 model：

```python
class ChatServiceProvider:
    def __init__(self, service, *, use_rag=False, model: str | None = None):
        self._service = service
        self._use_rag = use_rag
        self._session_id = None
        self._model = model    # NEW

    async def reply(self, user_text, history):
        sid = await self._ensure_session()
        async for event in self._service.generate(
            sid, user_text, use_rag=self._use_rag, model=self._model  # NEW
        ): ...
```

但 `ChatService.generate` 不接受 model！需要传到 `OllamaClient.chat_stream(messages, model=...)`。最干净是**让 `ChatService.generate` 多接一个 `model: str | None = None` 参数**透传。已存在的 SSE / WS / REST 调用全部不传，行为不变。

```python
# core/chat_service.py — generate signature
async def generate(self, session_id, user_text, *, use_rag=False, top_k=4,
                   abort=None, model: str | None = None) -> AsyncIterator[Event]:
    ...
    async for chunk in self._llm.chat_stream(messages, model=model):
        ...
```

零入侵。`/model qwen2.5:7b` 命令处理：

```python
async def _cmd_model(args: list[str]) -> None:
    if not args:
        # show list
        for m in state.available_models:
            mark = " *" if m == state.current_model else ""
            transcript.add_system(f"  {m}{mark}")
        return
    name = args[0]
    if name not in state.available_models:
        transcript.add_system(f"unknown model: {name}")
        return
    state.current_model = name
    services.provider._model = name   # type: ignore[attr-defined]
    transcript.add_system(f"model → {name}")
```

## 11. /register flow

类似 `/login`，多一个 `display_name` 可选输入：

```python
async def _cmd_register(args: list[str]) -> None:
    email = await _prompt("email: ")
    password = await _prompt("password (min 8, letter+digit): ", is_password=True)
    confirm = await _prompt("confirm: ", is_password=True)
    if password != confirm:
        transcript.add_error("register", "passwords don't match")
        return
    name = await _prompt("display name (optional): ")
    try:
        svc = await services.auth_service_factory()
        user = await svc.register(email, password, display_name=name or None)
    except EmailAlreadyExistsError:
        transcript.add_error("register", "email already registered, try /login")
        return
    transcript.add_system(f"registered as {user.email}; now run /login")
```

注意：`/register` 不自动登录——故意分两步，避免新手弄混"我注册了为什么 memory 还是 file"。

## 12. Backward compat

- `ui.chat_view.ChatView` 保留——给 `--legacy` mode 和 `tests/integration/test_cli_boot.py` 用。
- `app.chat_app.run_chat` 改名为 `run_tui_chat`；旧 `run_chat` 重命名 `run_legacy_chat`。
- `app/cli.py::main` 默认走 `run_tui_chat`，`--legacy` 走 `run_legacy_chat`。

## 13. Tests (lightweight)

- `tests/unit/ui/test_transcript_buffer.py`：append user / start_assistant / append_to_assistant / end_assistant / cap 1000，4 条。
- `tests/unit/ui/test_sessions_pane_render.py`：给 3 个 SessionMeta，断言渲染出的 ANSI 字符串包含正确符号 + cursor 高亮，2 条。
- `tests/unit/core/test_session_meta.py`：`FileChatMemory.list_session_metas` 现算 title（含中文 24 字截断），1 条。
- 全屏 TUI 不写集成测试 —— 现有 `test_cli_boot.py::test_main_help_exits_zero` + 新增 `test_legacy_mode_smoke` 覆盖启动路径。

## 14. Risks recap

| 风险 | 缓解 |
|---|---|
| prompt_toolkit 在 CI / 非 tty 环境炸 | `--legacy` flag 永远可用；`test_cli_boot` 只跑 legacy |
| 主区流式追加时光标乱跳 | `TextArea` 的 `read_only=True` + 自定义 `FormattedTextControl`，不用 TextArea 接收流 |
| 终端窗口 < 80 列布局崩 | sidebar `Conditional` 自动隐藏 (`width < 60`)；transcript wrap_lines=True |
| Ctrl+C 习惯被 Ctrl+Q 替代 | toolbar 永远显示快捷键提示；保留 Ctrl+C = exit（v2 改 abort） |
