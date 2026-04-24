# Proposal: Restructure CLI UI (opencode-style)

## Why

当前 `main.py` 把入口解析、会话编排、UI 渲染全部混在一起（`utils/console_ui.py` 又反过来承担视觉层）。这与 AGENTS.md §2、§3、§11 的目标架构严重冲突：

- §3 规定 `ui/` **不得** import `core/` / `db/` / `cache/` / `api/`。
- §11 规定 CLI 必须走 **opencode-style**（零 emoji、`│ ` 前缀、`rich.live` 流式渲染、`prompt_toolkit` 多行输入 + 历史 + toolbar）。
- §15 P1 要求：先独立 `ui/` 与 `app/`，让 `main.py` 变薄壳。

本次是整个重构的"破冰"步骤，为后续 P2~P7 腾出清晰的边界。

## What Changes

- 新增 `ui/` 模块，导出三个符号：`ChatView`、`PromptSession`、`Theme`。
- 新增 `app/` 模块：`app/cli.py`（argparse 子命令）、`app/chat_app.py`（交互式会话编排）。
- `main.py` 瘦身为 3~5 行：`from app.cli import main; main()`。
- `utils/console_ui.py` 改为 deprecated shim（`warnings.warn` 后 delegate 到 `ui.chat_view`），保留一个过渡窗口。
- 实现 opencode-style 渲染：零 emoji、角色色标（user=green / assistant=bright_cyan / system=grey50）、`│ ` 前缀、单行 banner `rag-chat · <model> · ready`。
- 输入走 `prompt_toolkit`：多行（Esc+Enter）、↑↓ 历史、底部 toolbar 显示快捷键。
- 引入斜杠命令统一分发器（`/quit /clear /new /model /retrieve on|off /login /logout`），暂未实装的命令返回友好 "not implemented yet" 提示。
- 流式输出通过 `rich.live.Live` 增量 Markdown 渲染，**接口层**预留 `AsyncIterator[Event]`，对齐未来 SSE/WS 的统一事件协议（§5.3）。

## Non-goals

- 不接入真正的 FastAPI / DB / 鉴权，登录命令先报 "login not enabled yet"。
- 不改 `utils/chat_memory.py` / `utils/model/*` 的内部实现（下一个 change 再搬）。
- 不删除 `utils/console_ui.py`（仅 deprecate，三次 PR 后才能删）。

## Impact

- **新增目录**：`ui/`、`app/`。
- **修改**：`main.py`（瘦身）、`utils/console_ui.py`（加 shim 警告）、`utils/__init__.py`（避免循环 import）。
- **依赖**：新增 `prompt_toolkit>=3.0`（rich 已有）。
- **风险**：中。`main.py` 入口形态变化，但 AGENTS.md §15 "兼容承诺" 要求 `python main.py` 必须仍能启动 CLI 聊天；因此必须保留 E2E 冒烟测试。
- **回退方式**：`git revert` 或把 `main.py` 重置回旧逻辑；`ui/` 和 `app/` 整个目录删除即可。
