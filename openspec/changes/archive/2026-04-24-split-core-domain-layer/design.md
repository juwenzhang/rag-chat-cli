# Design: Split `core/` Domain Layer

## Context

AGENTS.md §2 目标目录结构要求 `core/` 包含：

```
core/
├── llm/
│   ├── client.py          # 统一 LLM 抽象
│   ├── ollama.py          # Ollama 实现
│   └── trainer.py         # LoRA 训练封装
├── memory/
│   └── chat_memory.py     # 会话历史
├── knowledge/
│   └── base.py            # 知识库抽象（本次仍用文件，Change 9 接入 pgvector）
└── chat_service.py        # 聊天编排入口
```

当前 `utils/model/` 含 3 个文件（`model.py 9KB`、`ollama_client.py 14KB`、`trainer.py 10KB`），`utils/chat_memory.py 10KB`，`utils/knowledge_base.py 7KB`。它们彼此之间、以及对 `utils/logger.py`、`utils/config.py` 的依赖都需要梳理，避免搬家后出现循环 import。

## Goals / Non-Goals

**Goals**
- 按 §2 建立 `core/` 目录骨架。
- 所有 LLM / memory / knowledge 业务逻辑从 `utils/` 迁入 `core/`。
- 定义 `LLMClient` Protocol，把 Ollama 作为首个实现（未来可接 vLLM / OpenAI-compatible）。
- 新增 `ChatService`，作为 `app/` 与 `core/` 的唯一握手点。
- `utils/` 保留的 shim **不触发**任何运行时行为变化。

**Non-Goals**
- 不做 RAG 召回实现。
- 不改 LoRA 训练脚本的行为（仅改 import 路径）。
- 不接入数据库。

## Architecture

### 目录（本次完成后）

```
core/
├── __init__.py
├── chat_service.py
├── llm/
│   ├── __init__.py
│   ├── client.py          # Protocol + dataclass
│   ├── ollama.py          # OllamaClient(LLMClient)
│   └── trainer.py         # LoRATrainer (搬自 utils/model/trainer.py)
├── memory/
│   ├── __init__.py
│   └── chat_memory.py     # ChatMemory (async API)
└── knowledge/
    ├── __init__.py
    └── base.py            # KnowledgeBase (本次仍是 JSON 文件)
```

### `core/llm/client.py` —— 抽象协议

```python
from typing import Protocol, AsyncIterator
from dataclasses import dataclass

@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant", "system"]
    content: str

@dataclass(frozen=True)
class ChatChunk:
    delta: str
    done: bool = False
    usage: dict | None = None

class LLMClient(Protocol):
    async def chat_stream(
        self, messages: list[ChatMessage], *, model: str | None = None
    ) -> AsyncIterator[ChatChunk]: ...
    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]: ...
```

### `core/llm/ollama.py`

- 从 `utils/model/ollama_client.py` 迁入 + 重构：
  - **保留** 所有同步方法（打上 deprecated 注释，过渡期用）。
  - **新增** `async def chat_stream(...)` 返回 `AsyncIterator[ChatChunk]`（基于 `httpx.AsyncClient`）。
  - **新增** `async def embed(...)` 调用 `POST /api/embeddings`，支持批量。
- 构造参数 `base_url / timeout / default_chat_model / default_embed_model` 从 `settings.ollama` 读取。

### `core/memory/chat_memory.py`

- 迁入 `utils/chat_memory.py`。
- 对外接口改为 async：
  ```python
  class ChatMemory:
      async def get(self, session_id: str) -> list[ChatMessage]: ...
      async def append(self, session_id: str, msg: ChatMessage) -> None: ...
      async def new_session(self) -> str: ...
      async def list_sessions(self) -> list[str]: ...
  ```
- 底层暂仍写 `conversations/*.json`，但通过 `asyncio.to_thread` 包装，避免阻塞事件循环。
- 留 TODO: "replaced by DB persistence in change `setup-db-postgres-pgvector-alembic`"。

### `core/knowledge/base.py`

- 迁入 `utils/knowledge_base.py`。
- 抽象出 `KnowledgeBase` Protocol：
  ```python
  class KnowledgeBase(Protocol):
      async def search(self, query: str, *, top_k: int = 4) -> list[KnowledgeHit]: ...
  ```
- 本次实现 `FileKnowledgeBase`（基于现有 JSON 索引做关键词过滤）。
- 留 `PgvectorKnowledgeBase` TODO 占位，Change 9 实现。

### `core/chat_service.py`

```python
class ChatService:
    def __init__(self, llm: LLMClient, memory: ChatMemory, knowledge: KnowledgeBase | None = None):
        self._llm = llm
        self._memory = memory
        self._kb = knowledge

    async def generate(
        self, session_id: str, user_text: str, *, use_rag: bool = False
    ) -> AsyncIterator[Event]:
        # 1. 可选 RAG 召回（本次直接 yield 空 retrieval event 或跳过）
        # 2. 追加 user message 到 memory
        # 3. 调 LLM chat_stream，把 ChatChunk 适配成 Event
        # 4. done 事件后把 assistant message 追加到 memory
```

返回的 `Event` 对齐 AGENTS.md §5.3：`retrieval / token / done / error`。

### `app/chat_app.py` 切换

删除 `LegacyOllamaReplyProvider`，改为：

```python
from core.llm.ollama import OllamaClient
from core.memory.chat_memory import ChatMemory
from core.knowledge.base import FileKnowledgeBase
from core.chat_service import ChatService

def build_default_chat_service() -> ChatService:
    return ChatService(
        llm=OllamaClient.from_settings(settings),
        memory=ChatMemory.from_settings(settings),
        knowledge=FileKnowledgeBase.from_settings(settings) if settings.retrieval.enabled else None,
    )
```

### Shim 策略（保持兼容）

`utils/model/__init__.py`：

```python
import warnings
warnings.warn("utils.model is deprecated, use core.llm", DeprecationWarning, stacklevel=2)
from core.llm.ollama import OllamaClient  # noqa: F401
from core.llm.trainer import LoRATrainer as Trainer  # noqa: F401
```

`utils/chat_memory.py`：

```python
import warnings
warnings.warn("utils.chat_memory is deprecated, use core.memory.chat_memory", DeprecationWarning)
from core.memory.chat_memory import ChatMemory  # noqa: F401
```

`utils/knowledge_base.py` 同理。

## Alternatives Considered

- **把 trainer 也搬到 `workers/`**：AGENTS.md §2 明确 `trainer` 归 `core/llm/`，`workers/` 只放任务队列消费者；不挪。
- **直接删 `utils/` 旧文件**：会 break 外部引用（例如 `scripts/`），过渡一个版本更稳。

## Risks & Mitigations

- **循环 import**：`core/llm/ollama.py` 要不要 import `settings`？
  **缓解**：`OllamaClient` 不在构造函数里默认读 settings，改为 `@classmethod from_settings(cls, s: Settings)` 工厂方法。
- **async 改造引入行为差异**：同步 → async 可能导致异常传播时机变化。
  **缓解**：保留同步 `chat / embed` 方法（打 deprecated 警告），内部调 `asyncio.run(self.async_xxx(...))`；单元测试覆盖新旧两条路径。
- **`httpx` 并发连接池**：`OllamaClient` 生命周期要与 app 对齐。
  **缓解**：提供 `async def aclose()`；`app/chat_app.py` 在 shutdown 时调一次。

## Testing Strategy

- 单元：
  - `tests/unit/core/llm/test_ollama.py`：用 `respx` mock httpx，验证 `chat_stream` 能正确解析 NDJSON 流。
  - `tests/unit/core/memory/test_chat_memory.py`：临时目录，append + get 一致。
  - `tests/unit/core/knowledge/test_file_kb.py`：构造假 JSON 索引，search 返回 top-k。
  - `tests/unit/core/test_chat_service.py`：用 fake LLM (`FakeLLM` yield 固定 chunk) + in-memory ChatMemory，断言 event 流顺序 = retrieval? → token* → done。
- 集成：
  - `tests/integration/test_chat_app_with_core.py`：`ChatApp.run_one_turn("hi")` 走完整 `ChatService` 路径（LLM 用 fake），断言 ChatMemory 里多了 user + assistant 两条消息。
- 向后兼容：
  - `tests/unit/test_legacy_shims.py`：`from utils.model import OllamaClient` 能拿到类本身 + 触发 1 次 `DeprecationWarning`。
