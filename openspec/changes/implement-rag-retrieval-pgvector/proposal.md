# Proposal: Implement Real RAG Retrieval with pgvector

## Why

AGENTS.md §5.1 定义 `GET /knowledge/search`、§6-RAG 描述完整检索链路、§15 P6 明确：

> P6：RAG 召回：Embedding（`nomic-embed-text` via Ollama 或 `bge-small-zh-v1.5` 本地），chunking（按标题/段落），pgvector cosine 搜索 + top-k reranker（可选）。

前置 change 已经把"容器"建好：
- Change 4 建了 `chunks.embedding VECTOR(768)` + ivfflat 索引。
- Change 3 定义了 `KnowledgeBase` Protocol，占位 `FileKnowledgeBase`。
- Change 6 的 `/knowledge/search` 暂返回空列表。
- Change 8 的 `ingest_document` 任务为空壳。

**本次把"水"注满**：真正实现 chunking → embedding → 入库 → 向量召回 → top-k reranking → 在 `ChatService` 中作为 retrieval event 返回。

## What Changes

- 新增 `core/retrieval/` 模块：
  - `chunking.py` — 基于标题/段落切块，默认 `max_tokens=512, overlap=64`，支持 Markdown / 纯文本。
  - `embedding.py` — `Embedder` Protocol + `OllamaEmbedder` 实现（调 `OllamaClient.embed`）；预留 `SentenceTransformersEmbedder`（本次不实现，留 stub）。
  - `pgvector_store.py` — `PgvectorKnowledgeBase(KnowledgeBase)`，`search(query, top_k)` 用 `ORDER BY embedding <=> :vec`。
  - `reranker.py` — `Reranker` Protocol + `NoopReranker`（按召回分排）、`MMRReranker`（Maximal Marginal Relevance，纯 Python 实现）。
- `workers/tasks/ingest.py` 实装：
  1. 读 `documents.content`（或 `source` 下载）。
  2. `chunking.split(text) -> list[Chunk]`。
  3. 批量 `Embedder.embed`，落 `chunks` 表。
  4. 记录 `document.meta.ingest_stats`。
- `core/chat_service.py` 的 `generate(..., use_rag=True)` 真正调用 `KnowledgeBase.search` 并把结果作为 `retrieval` event + 注入 LLM system prompt。
- `api/routers/knowledge.py` 的 `GET /search` 真正调 `PgvectorKnowledgeBase.search`。
- 新增 CLI 子命令 `python main.py ingest <path>`：一键解析本地文件入库（便于冷启动）。
- 新增 prompt 模板 `core/chat_service/prompts.py`：
  ```
  You are a helpful assistant...
  Use the following retrieved context when helpful:
  ---
  {for hit in hits}
  [{i}] {hit.title} — {hit.snippet}
  {end}
  ---
  Cite as [n] when you use a source.
  ```

## Non-goals

- 不做跨语言 reranker（如 cohere / bge-reranker），只做 MMR。
- 不做 query rewriting / HyDE。
- 不做文档去重（hash 去重留 TODO）。
- 不做多种 embedding 模型的混合检索。
- 不做 citations 的严格校验（LLM 可能乱引用 [n]，本期不管）。

## Impact

- **新增**：`core/retrieval/`（4 个文件）、`core/chat_service_prompts.py`、`scripts/ingest_cli.py`。
- **修改**：`core/chat_service.py`（RAG 真实接入）、`core/knowledge/base.py`（新增 `PgvectorKnowledgeBase`）、`workers/tasks/ingest.py`（实装）、`api/routers/knowledge.py`（search 实装）、`app/cli.py`（`ingest` 子命令）。
- **依赖**：无需新增（用已有的 `pgvector` + `sqlalchemy` + `numpy`）。可选 `tiktoken>=0.7` 用于 token 计数。
- **风险**：中。embedding 维度、index 重建耗时、相似度阈值调参。
- **回退方式**：`settings.retrieval.enabled=False` → ChatService 不走 RAG；search 仍返回空。
