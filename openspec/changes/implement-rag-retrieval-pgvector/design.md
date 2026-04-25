# Design: RAG Retrieval with pgvector

## Context

AGENTS.md §6 概括了 RAG 全链路：
1. **Ingest**：解析 → 切块 → embedding → 入库。
2. **Retrieve**：query embedding → top-k 向量召回 → rerank。
3. **Augment**：把 top-k 拼进 system prompt。
4. **Generate**：LLM 生成（已由 Change 3/7 完成）。

本 change 的核心是 1~3。Embedding 模型默认选 `nomic-embed-text` via Ollama（768 维，已由 Change 4 的 migration 对齐）。

## Goals / Non-Goals

**Goals**
- **结构化切块**：Markdown 标题优先、段落次之、长段用滑动窗口回退。
- **批量 embedding**：对大文档分 batch 调 Ollama 避免单次超时。
- **pgvector cosine 召回**：使用 `embedding <=> :vec` 操作符配合 ivfflat 索引。
- **MMR rerank**：降低 top-k 中冗余，提升覆盖度。
- **可开关**：`settings.retrieval.enabled=False` 时所有 RAG 行为退化。

**Non-Goals**
- 不做 BM25 混合召回（后续 change 可加）。
- 不做 cross-encoder reranker（需额外模型）。

## Architecture

```
core/retrieval/
├── __init__.py
├── chunking.py        # split(text, *, doc_type, max_tokens, overlap) -> list[ChunkDraft]
├── embedding.py       # Embedder Protocol + OllamaEmbedder
├── pgvector_store.py  # PgvectorKnowledgeBase
├── reranker.py        # NoopReranker / MMRReranker
└── prompts.py         # RAG system prompt 模板
```

### `chunking.py`

```python
@dataclass(frozen=True)
class ChunkDraft:
    seq: int
    text: str
    title: str | None = None
    metadata: dict = field(default_factory=dict)

def split_markdown(text: str, *, max_tokens: int = 512, overlap: int = 64,
                   tokenizer=None) -> list[ChunkDraft]:
    """
    1. 用 `re.split(r"(?m)^(#{1,6} .+)$", text)` 按标题拆成 sections。
    2. 对每个 section 按段落（空行）再拆。
    3. 累积段落直到 >= max_tokens；若单段超过 max_tokens，走滑动窗口（step = max_tokens - overlap）。
    4. 返回 ChunkDraft 列表，title 继承最近的 H1/H2。
    """

def split_plain(text: str, **kwargs) -> list[ChunkDraft]: ...

def split(text: str, *, doc_type: Literal["md","txt","auto"] = "auto", **kwargs) -> list[ChunkDraft]:
    # 根据 doc_type 或 heuristic 选择策略
```

token 计数：有 `tiktoken` 则用；没有则用 `len(text.split())` 近似。

### `embedding.py`

```python
class Embedder(Protocol):
    dim: int
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class OllamaEmbedder(Embedder):
    def __init__(self, client: OllamaClient, *, model: str = "nomic-embed-text", dim: int = 768):
        self._c = client; self._model = model; self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # 批量：Ollama /api/embeddings 当前单发，手工并发 gather（限 concurrency）
        sem = asyncio.Semaphore(settings.retrieval.embed_concurrency)
        async def one(t: str) -> list[float]:
            async with sem: return await self._c.embed([t], model=self._model)[0]
        return await asyncio.gather(*(one(t) for t in texts))
```

### `pgvector_store.py`

```python
class PgvectorKnowledgeBase(KnowledgeBase):
    def __init__(self, session_factory, embedder: Embedder,
                 reranker: Reranker | None = None,
                 *, top_k_fetch: int = 20, top_k_final: int = 4):
        ...

    async def search(self, query: str, *, top_k: int | None = None) -> list[KnowledgeHit]:
        top_k = top_k or self._top_k_final
        vec = (await self._embedder.embed([query]))[0]
        async with self._sf() as s:
            stmt = (
                select(Chunk, Document.title.label("doc_title"),
                       (Chunk.embedding.cosine_distance(vec)).label("dist"))
                .join(Document, Document.id == Chunk.document_id)
                .order_by("dist")
                .limit(self._top_k_fetch)
            )
            rows = (await s.execute(stmt)).all()
        candidates = [
            KnowledgeHit(document_id=str(c.Chunk.document_id),
                         chunk_id=str(c.Chunk.id),
                         title=c.doc_title, content=c.Chunk.content,
                         score=1 - float(c.dist), source=c.doc_title or "")
            for c in rows
        ]
        return await self._reranker.rerank(query, candidates, top_k=top_k) if self._reranker \
               else candidates[:top_k]
```

注：`Chunk.embedding.cosine_distance(vec)` 由 `pgvector.sqlalchemy` 提供；对应 SQL 操作符 `<=>`。

### `reranker.py`

```python
class Reranker(Protocol):
    async def rerank(self, query: str, hits: list[KnowledgeHit], *, top_k: int) -> list[KnowledgeHit]: ...

class NoopReranker(Reranker):
    async def rerank(self, q, hits, *, top_k): return hits[:top_k]

class MMRReranker(Reranker):
    def __init__(self, embedder: Embedder, *, lambda_: float = 0.7): ...
    async def rerank(self, q, hits, *, top_k):
        # 需要 query + 每个 hit 的向量。复用 embedder。
        # MMR: argmax_i [λ * sim(q, d_i) - (1-λ) * max_j∈S sim(d_i, d_j)]
```

### `ChatService` 接入

```python
async def generate(self, session_id, user_text, *, use_rag=False, abort=None):
    hits: list[KnowledgeHit] = []
    if use_rag and self._kb:
        hits = await self._kb.search(user_text, top_k=settings.retrieval.top_k)
        yield RetrievalEvent(hits=[_to_proto(h) for h in hits]).model_dump()

    system_prompt = build_rag_system_prompt(hits) if hits else DEFAULT_SYSTEM_PROMPT
    messages = [ChatMessage("system", system_prompt), *history, ChatMessage("user", user_text)]
    # ... LLM stream
```

### `workers/tasks/ingest.py` 实装

```python
async def ingest_document(ctx: dict, document_id: str) -> dict:
    async with SessionLocal() as s:
        doc = await s.get(Document, UUID(document_id))
        if not doc: return {"ok": False, "reason": "not found"}
        text = doc.meta.get("content") or await _load_from_source(doc.source)

        drafts = split(text, doc_type="auto",
                       max_tokens=settings.retrieval.chunk_max_tokens,
                       overlap=settings.retrieval.chunk_overlap)

        embedder = OllamaEmbedder.from_settings()
        vectors = await embedder.embed([d.text for d in drafts])

        # 原子替换：先删旧 chunks 再写新
        await s.execute(delete(Chunk).where(Chunk.document_id == doc.id))
        s.add_all([
            Chunk(document_id=doc.id, seq=d.seq, content=d.text,
                  embedding=v, token_count=_count(d.text))
            for d, v in zip(drafts, vectors)
        ])
        doc.meta = {**doc.meta, "ingest_stats": {
            "chunks": len(drafts),
            "embed_model": embedder._model,
            "embed_dim": embedder.dim,
            "updated_at": datetime.utcnow().isoformat(),
        }}
        await s.commit()
    return {"ok": True, "chunks": len(drafts)}
```

### CLI `ingest` 子命令

```
python main.py ingest <path-or-glob> [--title TITLE] [--user me@example.com]
```

- 支持单文件、目录（递归扫描 `*.md *.txt`）。
- 每个文件先插入 `documents`，再 `enqueue("ingest_document", id)`（或 inline 执行）。

### Settings

```python
class RetrievalSettings(BaseModel):
    enabled: bool = True
    embed_model: str = "nomic-embed-text"
    embed_dim: int = 768
    embed_concurrency: int = 4
    chunk_max_tokens: int = 512
    chunk_overlap: int = 64
    top_k: int = 4
    top_k_fetch: int = 20
    reranker: Literal["noop", "mmr"] = "mmr"
    mmr_lambda: float = 0.7
```

## Alternatives Considered

- **LangChain / LlamaIndex**：重依赖、封装层厚；自写 4 个文件足矣。
- **Qdrant / Weaviate**：独立向量 DB，但 AGENTS.md §4 已定 pgvector。
- **按字符切块**：简单但质量差；按段落 + 标题更稳。

## Risks & Mitigations

- **风险**：大文件一次性 embedding 超时。
  **缓解**：`embed_concurrency` 限流 + 单 chunk 级别的 try/except，失败 chunk 标记 retry。
- **风险**：ivfflat 索引在数据量少时 recall 差。
  **缓解**：`lists=100` 是默认；文档 < 1000 时查询速度 OK，precision 也 OK；数据量增大后运维可 `REINDEX` 调 lists（运维文档里说明）。
- **风险**：embedding 维度与表结构不一致（换模型后维度变了）。
  **缓解**：启动 `init_retrieval()` 时从 `settings.retrieval.embed_dim` 读取并与 DB 探测的列维度比对，不一致则日志 error 并降级（不做自动 migration）。

## Testing Strategy

- 单元：
  - `tests/unit/core/retrieval/test_chunking.py`：Markdown 分标题、超长段滑窗。
  - `tests/unit/core/retrieval/test_mmr.py`：构造 3 个重复 + 2 个独立 hits，MMR 给出去重结果。
  - `tests/unit/core/retrieval/test_prompts.py`：build_rag_system_prompt 正确含 [1][2]。
- 集成（需 PG）：
  - `@pytest.mark.pg tests/integration/retrieval/test_pgvector_search.py`：插入 5 条 chunks + 假 embedding → search → 返回距离最近的 top-3。
  - `@pytest.mark.pg tests/integration/workers/test_ingest_end_to_end.py`：真实 Ollama mock + insert document → enqueue → 断言 chunks 表有行。
- 基线：
  - `python main.py ingest README.md` 成功后 `GET /knowledge/search?q=rag` 返回非空结果。
