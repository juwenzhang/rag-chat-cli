# Proposal: Split `core/` Domain Layer

## Why

当前 `utils/` 目录承担了过多角色：LLM 客户端、训练器、聊天记忆、知识库、任务调度、配置、日志、控制台 UI 全部混在一起（共 10+ 个文件、~50KB）。这严重违反 AGENTS.md §2 "目标目录结构" 和 §3 "依赖方向"：

- §2 规定 `core/` 应承载纯业务域：`llm/`、`memory/`、`knowledge/`、`chat_service.py`。
- §3 规定 `core/` **不得** import `api/`、`ui/`、`workers/`、`db/models/*`（只能依赖 `db.session` 抽象）。
- §15 P2 是继 P1（ui/app 分层）之后的第二个重构阶段，目的就是把业务域从 `utils/` 中抽出来。

本次把 **领域逻辑** 搬到 `core/`，保留 `utils/` 作为"纯工具函数容器"（logger、小 helper），为后续 P4（DB）、P5（API/SSE/WS）、P6（RAG 召回）奠定清晰边界。

## What Changes

- 新增 `core/` 目录，按 AGENTS.md §2 划分子模块：
  - `core/llm/` ← 搬 `utils/model/*`（`model.py`、`ollama_client.py`、`trainer.py`）
  - `core/memory/` ← 搬 `utils/chat_memory.py`
  - `core/knowledge/` ← 搬 `utils/knowledge_base.py`
  - `core/chat_service.py` ← **新建**：提供 `ChatService.generate(user_text, history, *, use_rag) -> AsyncIterator[Event]`，作为"编排入口"，把 llm + memory + knowledge 粘在一起（RAG 召回将在 Change 9 接入，本次先预留抽象）。
- `core/` 各文件内部改为 **async-first**：
  - `OllamaClient` 补充 `async def chat_stream()` / `async def embed()` 接口（同步方法暂保留 deprecated）。
  - `ChatMemory` 暴露 `async get / append / new_session` 接口（底层目前仍是文件 I/O，先用 `asyncio.to_thread` 包一下）。
- `app/chat_app.py` 的 `ReplyProvider` 实现替换：从 Change 2 的 `LegacyOllamaReplyProvider` 切到 `CoreChatServiceProvider`（内部调用 `ChatService`）。
- `utils/` 保留：`logger.py`、`config.py`（deprecated shim）、`console_ui.py`（deprecated shim）、`data_loader.py`、`task_scheduler.py`（后者将在 Change 8 迁到 `workers/`）。
- 所有对 `utils.model.*` / `utils.chat_memory` / `utils.knowledge_base` 的旧导入，在 `utils/__init__.py` 加 re-export shim + `DeprecationWarning`，**过渡一个版本后**清理。

## Non-goals

- 不引入数据库（记忆仍用文件 JSON；RAG 仍用现有 in-memory 知识库）。
- 不实现真正的 RAG 召回逻辑（Change 9 再做）。
- 不改 `scripts/lora_train.py` 的入口（训练器只做路径搬迁）。
- 不动 `utils/task_scheduler.py`（Change 8 迁移）。

## Impact

- **新增**：`core/__init__.py`、`core/llm/{__init__.py,client.py,ollama.py,trainer.py}`、`core/memory/{__init__.py,chat_memory.py}`、`core/knowledge/{__init__.py,base.py}`、`core/chat_service.py`。
- **修改**：`app/chat_app.py`（切换 provider）、`utils/__init__.py`（shim）、`utils/model/__init__.py`（deprecated）、`scripts/lora_train.py`（import 路径更新）。
- **迁移（git mv）**：`utils/model/*.py` → `core/llm/*.py`；`utils/chat_memory.py` → `core/memory/chat_memory.py`；`utils/knowledge_base.py` → `core/knowledge/base.py`。
- **风险**：中高。触及几乎所有现有业务文件；必须逐文件保留旧 API re-export。
- **回退方式**：`git revert`；旧 `utils/*.py` 路径仍有 shim 指向 `core/`，短期内不会 break。
