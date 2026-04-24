# Design: CLI UI Restructure (opencode-style)

## Context

AGENTS.md §11 给了 CLI 的视觉规范（零 emoji、`│ ` 前缀、色标、流式 Markdown），§3 明确了 `ui/` 的进/出依赖方向，§15 P1 是整个重构的第一步。当前 `utils/console_ui.py` 5.24KB 已混入鉴权提示、knowledge 操作等非 UI 内容，必须重新切分。

## Goals / Non-Goals

**Goals**
- 建立 `ui/` 纯展示层（禁止 import `core/`、`db/`、`cache/`）。
- 建立 `app/` 编排层（唯一可以同时知道 `ui/` 和 `core/` 的层）。
- `main.py` 瘦身为 shim，所有逻辑搬到 `app/cli.py`。
- 对齐 §5.3 事件协议，`ChatView.stream_assistant(events)` 的入参与未来 SSE/WS 的 event 结构一致。

**Non-Goals**
- 不实现真正的 LLM 调用；`app/chat_app.py` 用一个可注入的 `reply_provider` 抽象，先接 `utils/model/ollama_client.py` 兼容老路径。
- 不处理登录/鉴权命令的实际逻辑。

## Architecture

```
main.py (thin shell)
   │
   ▼
app/cli.py ── argparse sub-commands ──▶ chat / serve(stub) / train(stub) / ingest(stub)
   │
   ▼
app/chat_app.py
   │   ├── uses ──▶ ui.PromptSession     (input)
   │   ├── uses ──▶ ui.ChatView          (render)
   │   ├── uses ──▶ ui.Theme             (palette)
   │   └── calls ──▶ ReplyProvider       (abstract, today=Ollama legacy, tomorrow=core.chat_service)
   ▼
ui/ (pure presentation)
   ├── theme.py       palette + role colors
   ├── console.py     rich Console factory, banner
   ├── chat_view.py   Live + incremental Markdown
   ├── prompt.py      prompt_toolkit session + slash dispatcher
   └── markdown.py    safe Markdown rendering helpers
```

### `ui/theme.py`

```python
@dataclass(frozen=True)
class Theme:
    role_user: str = "green"
    role_assistant: str = "bright_cyan"
    role_system: str = "grey50"
    banner: str = "bold white"
    divider: str = "grey37"
    error: str = "red"
    ok: str = "green"
DEFAULT = Theme()
```

### `ui/chat_view.py` —— 对齐 §5.3 事件协议

```python
class Event(TypedDict, total=False):
    type: Literal["retrieval", "token", "done", "error", "ping", "pong"]
    delta: str
    hits: list[dict]
    message_id: str
    usage: dict
    duration_ms: int
    code: str
    message: str

class ChatView:
    def __init__(self, console: Console, theme: Theme = DEFAULT) -> None: ...
    def banner(self, model: str) -> None:
        self.console.print(f"[{self.theme.banner}]rag-chat · {model} · ready[/]")
    def user_echo(self, text: str) -> None: ...            # "│ [green]you[/] · ..."
    async def stream_assistant(self, events: AsyncIterator[Event]) -> None:
        """Consume Event iterator, use rich.live.Live to incrementally render Markdown."""
```

### `ui/prompt.py`

- 基于 `prompt_toolkit.PromptSession`。
- Key bindings：
  - `Esc, Enter` → submit
  - `Enter` → newline（默认行为）
  - `Ctrl-L` → clear screen
  - `Ctrl-C` / `Ctrl-D` → raise `EOFError` 给上层
- `bottom_toolbar` 文案：`Esc+Enter send · ↑↓ history · /help`。
- History：`FileHistory("~/.config/rag-chat/history")`。
- 暴露 `async def prompt_async(prompt: str = "› ") -> str`。

### 斜杠命令分发器

```python
# ui/prompt.py
class SlashDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[list[str]], Awaitable[None] | None]] = {}
    def register(self, name: str, fn): ...
    async def dispatch(self, line: str) -> bool:
        """Return True if line was a slash command (handled), False otherwise."""
```

`app/chat_app.py` 在启动时注册：
- `/quit` → 抛 `SystemExit`
- `/clear` → `console.clear()`
- `/new` → 清会话状态（调用下层 memory 的 new session）
- `/model <name>` → 占位，`warning: changing model not implemented yet`
- `/retrieve on|off` → 占位
- `/login` / `/logout` → 占位，提示 "available after auth change"

### `app/cli.py`

```python
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rag-chat")
    sub = p.add_subparsers(dest="cmd", required=False)
    sub.add_parser("chat", help="interactive chat")
    sub.add_parser("serve", help="(stub) run FastAPI server")
    sub.add_parser("train", help="(stub) LoRA train")
    sub.add_parser("ingest", help="(stub) ingest knowledge")
    return p

def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    match ns.cmd or "chat":
        case "chat":
            return asyncio.run(_run_chat())
        case _:
            print(f"'{ns.cmd}' not implemented yet")
            return 2
```

### `main.py`

```python
from app.cli import main
if __name__ == "__main__":
    raise SystemExit(main())
```

## Alternatives Considered

- **Textual**：比 rich + prompt_toolkit 重，学习曲线高；AGENTS.md §1 已冻结 `rich` + `prompt_toolkit`。
- **cleo / typer**：typer 依赖 click，argparse 对子命令够用且无额外依赖。

## Risks & Mitigations

- **风险**：`utils/console_ui.py` 的老 import 路径仍被 `utils/__init__.py` re-export。
  **缓解**：在 shim 中 `warnings.warn("utils.console_ui is deprecated ...")` 并 `from ui.chat_view import ChatView as ConsoleUI`（名字保持兼容）。
- **风险**：`prompt_toolkit` 的 `Esc+Enter` 在 Windows cmd 下可能不稳定。
  **缓解**：同时绑定 `F2` 为备用 submit；在 toolbar 提示。
- **风险**：`rich.live.Live` 与 `prompt_toolkit` 同时活跃时 ANSI 冲突。
  **缓解**：输入阶段 `Live.stop()`；assistant 开始渲染前 `Live.start()`。

## Testing Strategy

- 单元：
  - `tests/unit/ui/test_chat_view.py`：给定事件序列，`ChatView` 输出包含 expected Markdown 片段（用 `rich.console.Console(file=StringIO())`）。
  - `tests/unit/ui/test_prompt.py`：`SlashDispatcher` 注册 + dispatch 的单测。
- 集成：
  - `tests/integration/test_cli_boot.py`：`subprocess.run(["python", "main.py", "--help"])` 返回 0 且包含 `chat`。
- 手动冒烟：`python main.py chat` 能看到 banner、能回显用户输入、`/quit` 正常退出。
