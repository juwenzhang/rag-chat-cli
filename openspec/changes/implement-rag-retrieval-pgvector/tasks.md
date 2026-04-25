# Tasks: RAG Retrieval with pgvector

## 1. 依赖

- [ ] 1.1 `pyproject.toml` 可选新增：`tiktoken>=0.7`（dev 必装，runtime 软依赖，缺失时回退 split 统计）。
- [ ] 1.2 `numpy>=1.26`（MMR 的向量运算）。
- [ ] 1.3 `uv sync` 成功。

## 2. Settings 扩展

- [ ] 2.1 `settings.retrieval`：补齐 `enabled / embed_model / embed_dim / embed_concurrency / chunk_max_tokens / chunk_overlap / top_k / top_k_fetch / reranker / mmr_lambda`。
- [ ] 2.2 `.env.example` 对应补齐。
- [ ] 2.3 启动校验：`embed_dim` 必须与 DB `chunks.embedding` 维度一致（通过 `information_schema` 查询）。

## 3. Chunking

- [ ] 3.1 新建 `core/retrieval/__init__.py`。
- [ ] 3.2 `core/retrieval/chunking.py`：`ChunkDraft` dataclass + `split_markdown / split_plain / split`。
- [ ] 3.3 用正则拆 Markdown 标题保留层级；非 Markdown 回退段落。
- [ ] 3.4 token 计数：有 `tiktoken` 用 `get_encoding("cl100k_base")`，无则 `len(text.split())`。
- [ ] 3.5 单测：
  - 标题切分正确保留每段 title。
  - 单段超长时滑窗 step 正确。
  - overlap 覆盖相邻 chunk。

## 4. Embedding

- [ ] 4.1 `core/retrieval/embedding.py`：`Embedder` Protocol。
- [ ] 4.2 `OllamaEmbedder`：`from_settings()` 工厂，`embed(list[str])` 用 `asyncio.Semaphore` 限并发。
- [ ] 4.3 对空列表返回 `[]`；对空串 raise `ValueError`。
- [ ] 4.4 单测：用 `respx` mock Ollama `/api/embeddings`，验证批量调用。

## 5. pgvector store

- [ ] 5.1 `core/retrieval/pgvector_store.py`：`PgvectorKnowledgeBase`。
- [ ] 5.2 `search` 用 SQLAlchemy `Chunk.embedding.cosine_distance(vec)`；JOIN document 取 title。
- [ ] 5.3 `KnowledgeHit` 扩展字段：`chunk_id`、`document_id`、`title`、`content`、`score`（= 1 - distance）。
- [ ] 5.4 `from_settings(session_factory, llm_client)` 工厂构造 `Embedder` + `Reranker` + 自身。
- [ ] 5.5 单测（PG 标记）：插入固定 embedding 验证 top-k 顺序。

## 6. Reranker

- [ ] 6.1 `core/retrieval/reranker.py`：`Reranker` Protocol + `NoopReranker` + `MMRReranker`。
- [ ] 6.2 `MMRReranker.rerank` 内部对 hits 调 `embedder.embed` 取向量（或让调用方把向量带进来，减少一次调用）。
- [ ] 6.3 单测：
  - 构造 5 个 hit，其中前 3 个内容接近，后 2 个独立。
  - λ=0.7 时 top_k=3 应含至少 1 个"独立"hit。
  - λ=1.0 退化为 Noop。

## 7. Prompts

- [ ] 7.1 `core/retrieval/prompts.py`：`DEFAULT_SYSTEM_PROMPT`、`build_rag_system_prompt(hits, user_prefix=None) -> str`。
- [ ] 7.2 拼接样式含 `[n]` 编号，snippet 截断到 500 字符。
- [ ] 7.3 单测：无 hits 返回 default；有 hits 含 `[1]` `[2]`。

## 8. ChatService 接入

- [ ] 8.1 `core/chat_service.py` 的 `generate`：
  - 若 `use_rag` 且 `self._kb`：先 `hits = await kb.search(user_text, top_k=settings.retrieval.top_k)`。
  - yield `RetrievalEvent(hits=[...])`。
  - 用 `build_rag_system_prompt(hits)` 作为 system prompt。
- [ ] 8.2 `build_default_chat_service()` 按 `settings.retrieval.enabled` 选 `PgvectorKnowledgeBase` 或 `None`。
- [ ] 8.3 单测：fake KB + fake LLM，断言 retrieval event 在第一个 yield，system prompt 包含 snippet。

## 9. Ingest 任务实装

- [ ] 9.1 `workers/tasks/ingest.py`：按 design 完整实现。
- [ ] 9.2 原子替换策略：先 `DELETE chunks WHERE document_id=:id`，再批量 `INSERT`；外层事务。
- [ ] 9.3 错误处理：单个 chunk embedding 失败 → 记日志、跳过，继续其他。
- [ ] 9.4 写入 `document.meta.ingest_stats`。
- [ ] 9.5 单测（SQLite，fake Embedder）：document → ingest → chunks 表行数正确。

## 10. API search 实装

- [ ] 10.1 `api/routers/knowledge.py` 的 `GET /search`：从 app.state 取 `kb`（lifespan 里 build），调 `kb.search`。
- [ ] 10.2 返回 `list[SearchHitOut]`（从 `KnowledgeHit` 映射）。
- [ ] 10.3 `top_k` 入参 clamp 到 `[1, 20]`。
- [ ] 10.4 单测：上传 + ingest（inline queue）+ search 返回命中。

## 11. CLI `ingest` 子命令

- [ ] 11.1 `app/cli.py` 新增 `ingest` 子解析器：`path(s) / --title / --user / --glob`。
- [ ] 11.2 `scripts/ingest_cli.py` 或直接在 `app/ingest_cli.py`：扫描文件 → 创建 Document → enqueue。
- [ ] 11.3 打印进度条（用 rich，若 UI 不可用退化为每文件一行）。
- [ ] 11.4 `python main.py ingest README.md --title "repo readme"` 测试跑通。

## 12. 测试

- [ ] 12.1 `tests/unit/core/retrieval/` 四件：chunking、embedding、mmr、prompts。
- [ ] 12.2 `tests/integration/retrieval/test_pgvector_search.py`（`@pytest.mark.pg`）。
- [ ] 12.3 `tests/integration/workers/test_ingest_end_to_end.py`（`@pytest.mark.pg`）。
- [ ] 12.4 `tests/api/test_search_with_rag.py`。
- [ ] 12.5 `uv run pytest -q -m "not pg and not redis"` 全绿。

## 13. 质量与文档

- [ ] 13.1 `ruff check core/retrieval` 无错。
- [ ] 13.2 `mypy --strict core/retrieval` 无错。
- [ ] 13.3 `docs/RAG.md` 新文档：ingest 流程、chunking 参数选择、ivfflat 调优指南。
- [ ] 13.4 README 加 quick start：`python main.py ingest docs/*.md && python main.py chat --rag`。
- [ ] 13.5 AGENTS.md §19 追加 "RAG retrieval with pgvector + MMR"。

## 14. 冒烟

- [ ] 14.1 `docker compose --profile db up -d postgres` + `alembic upgrade head`。
- [ ] 14.2 `ollama pull nomic-embed-text`（本地已有 Ollama）。
- [ ] 14.3 `python main.py ingest AGENTS.md --title "agents"` 成功，`chunks` 表出现新行。
- [ ] 14.4 `python main.py serve` + `curl 'http://localhost:8000/knowledge/search?q=cli'` 返回非空 hits。
- [ ] 14.5 `python main.py chat` 下 `/rag on` 后问 "what is the CLI UX spec?"，回复中出现 `[1]` 引用 + retrieval 卡片。
