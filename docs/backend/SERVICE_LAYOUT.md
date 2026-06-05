# Service Layer Layout

后端业务层 `service/` 的模块清单、依赖方向和后续重构计划。

> **范围**：`service/` 包；`api/`（HTTP/WS 入口层）、`alembic/`（迁移）、`scripts/`（运维脚本）只能依赖 `service/`，反向禁止。

## 1. 当前模块清单

| 模块 | 行数级 | 职责 | 主要消费者 |
| --- | --- | --- | --- |
| `service/auth/` | ~1.5k | 注册 / 登录 / 密码 hash / token 签发 | `api/routers/auth.py` |
| `service/chat/` | ~3k | 会话编排（`ChatService`）、prompt 拼装、token 预算、标题生成、并发限流 | SSE/WS/REST 三个 chat router |
| `service/common/` | ~210 | 可观测性 helper（usage 累加、tracer） | `service/chat/service.py` |
| `service/db/` | ~1.6k | SQLAlchemy 异步 base / session / models（19 张表） | 全栈 |
| `service/evaluation/` | ~130 | 答案评估（用本地 LLM 打分） | `api/routers/chat.py` |
| `service/knowledge/` | ~1.4k | RAG：retriever Protocol + pgvector 实现 + ingestion + reranker + reflection | chat / knowledge router |
| `service/llm/` | ~1.3k | LLM 客户端：`LLMClient` Protocol + Ollama / OpenAI 实现 + HTTP 错误分类 | chat / providers / evaluation |
| `service/mcp/` | ~480 | MCP（Model Context Protocol）stdio 客户端 + tool 适配 | tools 注册 |
| `service/memory/` | ~600 | 会话记忆（`DbChatMemory`）+ 用户长期记忆（`UserMemoryStore`） | chat |
| `service/orgs/` | ~50 | 组织成员策略（角色/权限） | `api/routers/orgs.py`、`api/routers/wiki.py` |
| `service/providers/` | ~1k | Provider 注册表 + 加密存储 + runtime 解析 + model_kinds | chat factory / providers router |
| `service/storage/` | ~1.2k | 对象存储抽象（local / S3）+ 图片 / vision 元数据 | assets router |
| `service/streaming/` | ~300 | SSE/WS 事件类型、错误码 enum、abort 控制 | chat / api routers |
| `service/tools/` | ~500 | 工具注册表 + 内建工具（codebase / web） | chat factory |
| `service/wiki/` | ~60 | wiki 角色策略 | `api/routers/wiki.py` |
| `service/workers/` | ~360 | Redis 队列 + worker 进程（P5 已写但未投产） | （暂无） |
| `service/errors.py` | 17 | 跨模块通用业务异常（`NotFoundError` / `ForbiddenError`） | 全栈 |

## 2. 依赖方向

```
api/, alembic/, scripts/
        │
        ▼
   ┌─────────────────────────────────────────────┐
   │                 service/                    │
   │                                             │
   │   chat ─┬─► memory ──► db                   │
   │         ├─► knowledge ──► db                │
   │         ├─► llm                             │
   │         ├─► tools ──► mcp                   │
   │         └─► providers ──► db                │
   │                                             │
   │   auth ──► db                               │
   │   storage ──► db                            │
   │   evaluation ──► llm                        │
   │   workers (independent runtime)             │
   │   common, errors (utilities)                │
   └─────────────────────────────────────────────┘
```

**约束**：
1. `service/db/` 不依赖任何同级业务模块，是底层基础设施。
2. `service/chat/` 是聚合根，会拉所有下游模块。
3. `service/streaming/` 只导出协议常量与轻量类型，不依赖 chat。
4. `service/workers/` 独立进程入口，未来 enqueue 的生产端可以是任何模块。

## 3. 已清理的死代码

| 删除 | 原因 |
| --- | --- |
| `service/knowledge/local.py`（`FileKnowledgeBase`） | TUI/Web 全部走 server，离线 JSONL 检索器无实际使用 |
| `service/memory/chat_memory.py::FileChatMemory` | 同上，会话改纯 DB 持久化 |
| `service/chat/factory.py::build_chat_service()` | 上述两者唯一调用入口 |
| `api/chat_deps.py::get_chat_service()` | factory 的 FastAPI 包装，无路由消费 |

> 知识库与会话现在是**纯 CS 架构**：所有客户端必登录，所有数据落 Postgres。

## 4. 待重构方向（折中扁平 DDD）

未来分批迁移，**不一刀切**。每批控制在 1 PR ≤ 800 行 diff。

### 4.1 目标分层

```
service/
├── core/          # 跨域共享：errors, observability, abort, streaming events
├── platform/      # 基础设施：redis, db, storage, http client
├── http/          # 出站 HTTP / SSE / WS 客户端封装（区别于 api/ 入站）
├── llm/           # LLM 客户端 + 错误分类（已就位）
├── domain/        # 业务聚合：chat / knowledge / memory / auth / orgs / wiki
└── workers/       # 后台任务执行器
```

### 4.2 迁移分批

| 批次 | 内容 | 风险 |
| --- | --- | --- |
| **B1** | `errors.py` + `common/observability.py` + `streaming/` → `core/` | 低，只动 import |
| **B2** ✅ | `platform/redis.py`（单例 + cache + 限流），LLM 路由限流装饰器 | 已落地，详见 [`REDIS_INTEGRATION.md`](REDIS_INTEGRATION.md) |
| **B3** | `storage/` → `platform/storage/` | 低 |
| **B4** | `chat/`、`knowledge/`、`memory/`、`auth/`、`orgs/`、`wiki/` → `domain/<name>/` | 中，import 量大但机械 |
| **B5** | `tools/`、`mcp/` → `domain/tools/`，重新整理工具注册表 | 中 |
| **B6** | `evaluation/` 收口到 `domain/chat/evaluation.py` | 低 |

每批结束后写入 `docs/backend/` 一份 ADR（架构决策记录）。

### 4.3 Redis 三件套接入计划

- **缓存**：高频只读查询（model registry、provider config、user limits）走 `platform.redis.cache`，TTL 装饰器。
- **队列**：`workers/queue.py` 已就位，未来 ingestion / 长任务生产端切到队列。
- **限流**：滑动窗口装饰器装在 LLM 客户端外层和按 user_id 装在路由层，配合刚加的 `LLMRateLimitError` / `FlowErrorCode.RATE_LIMITED`。

## 5. 强制约束

- ✅ `api/` 只能 import `service.*`，不能反向。
- ✅ `service/db/models/` 不能 import `service.<domain>`（避免循环）。
- ✅ 所有错误码、事件类型、消息角色字面量都走 `service/streaming/error_codes.py` 与各域 `enum.py`，**禁止散落字符串**。
- ✅ 所有 LLM 调用必须经过 `service/llm/_http_errors.py::classify_http_error`。
- ❌ 不再新增 file-backed 实现，知识库 / 会话 / 任意持久化只走 DB 或 Redis / 对象存储。
