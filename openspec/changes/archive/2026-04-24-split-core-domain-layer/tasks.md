# Tasks: Split `core/` Domain Layer

> v0.6 note — v0.4 干净化已整体删除 `utils/` 目录，原"迁移/shim"类任务失去对象，
> 统一标记为 **[x] (N/A - cleanup supersedes)**；有效任务照常完成。详见 AGENTS.md §19。

## 1. 骨架与空目录

- [x] 1.1 新建 `core/__init__.py`（空）。
- [x] 1.2 新建 `core/llm/__init__.py`、`core/memory/__init__.py`、`core/knowledge/__init__.py`。
- [x] 1.3 `core/__init__.py` 加 `__all__ = []`，明确禁止 re-export 内部实现（让用户走子模块）。

## 2. `core/llm/client.py`（抽象）

- [x] 2.1 定义 `ChatMessage`、`ChatChunk` 两个 `@dataclass(frozen=True)`。
- [x] 2.2 定义 `LLMClient Protocol`（`chat_stream` + `embed` + `aclose`）。
- [x] 2.3 定义 `LLMError` 基础异常类（供 Ollama / 未来 OpenAI 共用）。
- [x] 2.4 单测：Protocol 用 `runtime_checkable`，`isinstance(fake_impl, LLMClient)` 通过。

## 3. 迁移 Ollama 客户端 → `core/llm/ollama.py`

- [x] 3.1 (N/A - cleanup supersedes) ~~`git mv utils/model/ollama_client.py core/llm/ollama.py`~~；`utils/model/` 已在 v0.4 删除，改为直接新建 `core/llm/ollama.py`。
- [x] 3.2 (N/A - cleanup supersedes) ~~修正文件内的相对 import~~；新文件直接 `from settings import settings`。
- [x] 3.3 新增 `async def chat_stream(messages, *, model=None) -> AsyncIterator[ChatChunk]`，基于 `httpx.AsyncClient` 消费 NDJSON。
- [x] 3.4 新增 `async def embed(texts, *, model=None) -> list[list[float]]`，POST `/api/embeddings`。
- [x] 3.5 新增 `async def aclose()`，关闭内部 `AsyncClient`。
- [x] 3.6 (N/A - cleanup supersedes) ~~旧同步 `chat / embed` 方法~~；v0.4 已删除旧同步实现，无"旧方法"可包装。
- [x] 3.7 `@classmethod def from_settings(cls, s=None) -> "OllamaClient"`。
- [x] 3.8 `__repr__` 输出 `OllamaClient(base_url=..., chat_model=...)`。

## 4. 迁移 Trainer → `core/llm/trainer.py`

- [x] 4.1 (N/A - cleanup supersedes) `utils/model/trainer.py` 与 `scripts/lora_train.py` 已在 v0.4 删除；trainer 迁移推迟到未来单独 change（需先重建训练入口）。
- [x] 4.2 (N/A - cleanup supersedes)
- [x] 4.3 (N/A - cleanup supersedes)
- [x] 4.4 (N/A - cleanup supersedes)
- [x] 4.5 (N/A - cleanup supersedes)

## 5. 处理 `utils/model/model.py`

- [x] 5.1 (N/A - cleanup supersedes) 文件已在 v0.4 删除，无需合并/改名。
- [x] 5.2 (N/A - cleanup supersedes)
- [x] 5.3 (N/A - cleanup supersedes)

## 6. 迁移 ChatMemory → `core/memory/chat_memory.py`

- [x] 6.1 (N/A - cleanup supersedes) ~~`git mv utils/chat_memory.py ...`~~；v0.4 已删除，改为直接新建。
- [x] 6.2 将核心 IO 方法实现为 async：`get / append / new_session / list_sessions / delete_session`。
- [x] 6.3 文件 IO 走 `await asyncio.to_thread(...)`。
- [x] 6.4 `@classmethod from_settings(cls, s=None)`，默认路径 `./conversations`。
- [x] 6.5 `append` 同步快照写盘（写 `*.tmp` → `os.replace`），避免半写文件。
- [x] 6.6 在类注释里留 TODO：`# will be replaced by DB-backed implementation in change setup-db-postgres-pgvector-alembic`。

## 7. 迁移 KnowledgeBase → `core/knowledge/base.py`

- [x] 7.1 (N/A - cleanup supersedes) ~~`git mv utils/knowledge_base.py ...`~~；v0.4 已删除，改为直接新建。
- [x] 7.2 抽出 `class KnowledgeBase(Protocol)`：`async def search(query, *, top_k=4) -> list[KnowledgeHit]`。
- [x] 7.3 `FileKnowledgeBase` 作为占位实现（空 hits），真实检索留给 P7。
- [x] 7.4 定义 `@dataclass(frozen=True) KnowledgeHit(title, content, score, source)`。
- [x] 7.5 预留 `# class PgvectorKnowledgeBase: ...` 占位注释（Change 9 实现）。

## 8. 新建 `core/chat_service.py`

- [x] 8.1 实现 `class ChatService` 含 `__init__(llm, memory, knowledge=None)`。
- [x] 8.2 实现 `async def generate(session_id, user_text, *, use_rag=False, top_k=4) -> AsyncIterator[Event]`。
- [x] 8.3 `use_rag=True` 且 `self._kb` 非空时，先 `yield {"type": "retrieval", "hits": [...]}`。
- [x] 8.4 LLM 的 `ChatChunk` 适配成 `{"type": "token", "delta": chunk.delta}`。
- [x] 8.5 流结束 `yield {"type": "done", "usage": ..., "duration_ms": ...}`。
- [x] 8.6 异常 → `yield {"type": "error", "code": "...", "message": str(e)}`，并不重新抛出。
- [x] 8.7 `done` 后把完整 user + assistant 消息追加到 memory。

## 9. 集成到 `app/chat_app.py`

- [x] 9.1 删除 `LegacyOllamaReplyProvider`（v0.5 起就用 Echo 占位，本次保留 Echo 作 fallback）。
- [x] 9.2 新增 `ChatServiceProvider`，`build_default_chat_service()` / `build_default_provider()` 工厂函数。
- [x] 9.3 应用启动时构造 ChatService；关闭时 `await provider.aclose()`（级联关 ollama client）。
- [x] 9.4 `/new` 命令触发 `ChatServiceProvider.reset_session()` 返回新 session id。

## 10. 兼容 shim

- [x] 10.1 (N/A - cleanup supersedes) `utils/` 目录已在 v0.4 整体删除，无 shim 可加。
- [x] 10.2 (N/A - cleanup supersedes)
- [x] 10.3 (N/A - cleanup supersedes)
- [x] 10.4 (N/A - cleanup supersedes)

## 11. 测试

- [x] 11.1 `tests/unit/core/test_llm_client.py`（Protocol 结构 + ChatMessage/ChatChunk 冻结行为）。
- [x] 11.2 `tests/unit/core/test_chat_memory.py`（tmp_path，roundtrip / delete / 非法 session id）。
- [x] 11.3 `tests/unit/core/test_knowledge_base.py`（FileKnowledgeBase 空返回）。
- [x] 11.4 `tests/unit/core/test_chat_service.py`（happy / retrieval / LLM error 三路径）。
- [x] 11.5 (N/A - cleanup supersedes) ~~`tests/unit/test_legacy_shims.py`~~；无 shim 可测。
- [x] 11.6 `uv run pytest -q` 全绿（32 passed）。

## 12. 质量门与文档

- [x] 12.1 `ruff check core/ app/ tests/unit/core/` 无错。
- [x] 12.2 `uvx mypy --strict core/ app/ ui/ --explicit-package-bases` 无错（18 files checked）。
- [x] 12.3 (N/A - cleanup supersedes) ~~更新 `docs/ARCHITECTURE.md`~~；v0.4 已删除整个 `docs/`，改为在 AGENTS.md §19 v0.6 条目记录依赖方向。
- [x] 12.4 AGENTS.md §19 Change Log 追加 v0.6 / P2 完成条目。

## 13. 冒烟

- [x] 13.1 `python main.py chat` 能正常聊天；ollama 可达时走 ChatService、不可达时自动 fallback 到 Echo；`/new` 生成新 session，`/quit` 干净退出。
- [x] 13.2 `grep -R "utils\.(model|chat_memory|knowledge_base)"` 业务代码 0 命中（仅 openspec 文档引用）。
- [x] 13.3 同上，一次 grep 覆盖三个模块名。
