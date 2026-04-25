# Design: Switch ChatMemory to DB backend

## 1. Protocol shape

```python
# core/memory/chat_memory.py

class ChatMemory(Protocol):
    async def new_session(self) -> str: ...
    async def list_sessions(self) -> list[str]: ...
    async def get(self, session_id: str) -> list[ChatMessage]: ...
    async def append(self, session_id: str, msg: ChatMessage) -> None: ...
    async def delete_session(self, session_id: str) -> None: ...
```

`session_id` 对外统一是 **小写 hex 的 UUID 字符串**（`"9f0e…"`，无连字符也行但我们用带连字符的标准形式）；`DbChatMemory` 内部 `uuid.UUID(sid)` 转换；`FileChatMemory` 继续当 opaque 字符串用。

**为什么不直接换成 `uuid.UUID`**：`core/chat_service.py` 和 `ui/chat_view.py` 都有 `session_id: str` 签名；换类型要波及三四个文件 + 一堆测试。string 足够表达 uuid；DB 层就地转。

## 2. DbChatMemory 结构

```python
class DbChatMemory:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        user_id: uuid.UUID,
    ) -> None:
        self._sf = session_factory
        self._user_id = user_id

    async def new_session(self) -> str:
        async with self._sf() as s:
            row = ChatSession(user_id=self._user_id, title=None)
            s.add(row)
            await s.commit()
            return str(row.id)

    async def get(self, session_id: str) -> list[ChatMessage]:
        sid = uuid.UUID(session_id)
        async with self._sf() as s:
            # cross-user isolation — callers can only read their own sessions
            owner_q = select(ChatSession.user_id).where(ChatSession.id == sid)
            owner = await s.scalar(owner_q)
            if owner is None or owner != self._user_id:
                return []
            q = (
                select(Message)
                .where(Message.session_id == sid)
                .order_by(Message.created_at.asc())
            )
            rows = (await s.scalars(q)).all()
            return [ChatMessage(role=r.role, content=r.content) for r in rows]

    async def append(self, session_id: str, msg: ChatMessage) -> None:
        sid = uuid.UUID(session_id)
        async with self._sf() as s:
            s.add(Message(session_id=sid, role=msg.role, content=msg.content))
            await s.commit()

    async def delete_session(self, session_id: str) -> None:
        sid = uuid.UUID(session_id)
        async with self._sf() as s:
            row = await s.get(ChatSession, sid)
            if row is None or row.user_id != self._user_id:
                return
            await s.delete(row)  # FK cascade kills messages
            await s.commit()

    async def list_sessions(self) -> list[str]:
        async with self._sf() as s:
            q = (
                select(ChatSession.id)
                .where(ChatSession.user_id == self._user_id)
                .order_by(ChatSession.updated_at.desc())
            )
            rows = (await s.scalars(q)).all()
            return [str(r) for r in rows]
```

**关键点**：
- 每个方法一个 `async with session_factory()`；**不要**在 `__init__` 里持有 session——会话级对象，生命周期 ≠ ChatMemory 实例。
- `get()` 先验证 `owner == user_id`，避免"伪造 session_id 读他人历史"的风险；虽然路由层也校验，但 defense-in-depth。
- `append()` 不更新 `chat_sessions.updated_at` —— `TimestampMixin` 的 `onupdate=func.now()` 只在 UPDATE `chat_sessions` 行本身时触发。想让 `list_sessions` 按活跃度排序需要显式 `session.updated_at = func.now()`；本 change **暂不做**，`list_sessions` 按 `updated_at desc` 在空值情况下退化为 `created_at` 的等价排序——够用。

## 3. ChatService 连接方式

`ChatService.__init__` 已经接受 `ChatMemory`（现在升级为 Protocol）。唯一变化是 `ChatService.new_session()` 的语义：

- `FileChatMemory`：`secrets.token_hex(8)`（16 hex chars）
- `DbChatMemory`：`str(uuid.uuid4())`（36 chars 含 `-`）

两种字符串都能被 `ui/chat_view.py` / `api/routers/chat_stream.py` 当不透明字符串处理，**除了** REST 侧要 `uuid.UUID(session_id)` 校验——DB backend 返回的本来就是合法 UUID 字符串，不会断。

## 4. Wiring

### 4.1 `api/chat_service.py`

```python
# NEW signature — factory now needs user_id.
async def build_chat_service_for_user(
    user: User = Depends(get_current_user),
    session_factory: async_sessionmaker = Depends(get_session_factory),
) -> ChatService:
    llm = OllamaClient.from_settings(settings)
    memory = DbChatMemory(session_factory, user.id)
    kb = FileKnowledgeBase.from_settings(settings) if settings.retrieval.enabled else None
    return ChatService(llm=llm, memory=memory, knowledge=kb)


# Keep the old `get_chat_service` for tests; it defaults to file-backed.
def get_chat_service() -> ChatService:
    return build_chat_service()  # file-backed
```

注意 FastAPI dep 不能返回 `async` 函数结果时带多参 yield（需要 aclose 清理 LLM）；保持当前"非 yield dep + 路由 try/finally 显式 aclose"的模式，Change 7 已经设计成这样，本 change 不动。

新增 `get_session_factory()`：return `current_session_factory()`；测试时 override。

### 4.2 路由改动

`api/routers/chat.py::post_message` 原来：
```python
# old
user_msg = Message(session_id=..., role="user", content=...)
session.add(user_msg)
assistant_text, tokens = await _generate_reply(service, body)
asst = Message(session_id=..., role="assistant", content=..., tokens=tokens)
session.add(asst)
await session.commit()
```

改成：
```python
# new — ChatService owns persistence now
result = await service.generate_full(str(body.session_id), body.content, use_rag=body.use_rag)
if result["error"] is not None:
    raise HTTPException(502, ...)
# We still need tokens/message_id for the response — do one SELECT:
last_assistant = await session.scalar(
    select(Message)
    .where(Message.session_id == body.session_id, Message.role == "assistant")
    .order_by(Message.created_at.desc())
    .limit(1)
)
return MessageOut.model_validate(last_assistant)
```

多一次 SELECT 换来"service 是 single writer"的单语义，值。

`api/routers/chat_stream.py` / `api/routers/chat_ws.py` 原来是 `_persist_turn(...)` 由路由手写进 DB；**改为删掉路由层的 `_persist_turn`**，让 `ChatService` 内部（通过 `DbChatMemory`）去写。

### 4.3 CLI

```python
# app/chat_app.py::build_default_chat_service
async def build_default_chat_service() -> Any:
    from app import auth_local
    from core.auth.tokens import decode_token
    from core.auth.errors import TokenExpiredError, TokenInvalidError

    pair = auth_local.load()
    memory: ChatMemory
    if pair:
        try:
            payload = decode_token(pair.access_token, expected_type="access")
            user_id = uuid.UUID(payload.sub)
            init_engine()
            memory = DbChatMemory(current_session_factory(), user_id)
        except (TokenExpiredError, TokenInvalidError, Exception):
            memory = FileChatMemory.from_settings(settings)  # fallback
    else:
        memory = FileChatMemory.from_settings(settings)
    ...
```

启动横幅多一行 `memory: db(user_id=...)` or `memory: file (offline)`，开发者一眼看清模式。

## 5. Tests (lightweight — per user instruction)

Change 8 的 REST/SSE/WS 端到端测试已经覆盖"发消息 → DB 有行"；本 change 需要：

- **1 条 DbChatMemory 单测**（`tests/unit/core/test_db_chat_memory.py`）：
  roundtrip — new_session → append user → append assistant → get 拿回两条 → delete → get 返空。跑 SQLite in-memory (`async_engine` fixture)。
- **1 条 cross-user 单测**：user A 建 session，user B 的 DbChatMemory.get 该 session 返回 `[]`。
- **修订 `tests/unit/core/test_chat_service.py`** —— 把 `ChatMemory(root=tmp_path)` 改成 `FileChatMemory(root=tmp_path)`（类改名）。
- **修订 `tests/api/conftest.py`** —— 如果 `get_chat_service` override 还要用 file backend 就不改；如果 override 要走 DB backend，改掉工厂即可。实际上测试用 `FakeLLM + FileChatMemory(tmp_path)` 更简单，保持。
- **不写** 纯集成 REST+DB backend 的端到端测试（Change 7 的 `tests/api/test_sse_stream.py` 已经覆盖端到端，改完把那里的 "after-SSE 查 messages 表" 断言加一下即可）。

## 6. 向后兼容

- **导出**：`core/memory/chat_memory.py` 顶层 **同时** 保留 `ChatMemory`（Protocol）、`FileChatMemory`、`DbChatMemory`。
- 旧代码 `from core.memory.chat_memory import ChatMemory` 继续能 import，只是现在是 Protocol；`ChatMemory(root=...)` 的老用法**会炸**（Protocol 不能实例化）——**一次性找完所有调用点**改成 `FileChatMemory(root=...)`。grep `ChatMemory(` 命中 ≤ 10 处，可控。

## 7. Risks

- **测试 FakeLLM + DbChatMemory 组合是否跑得动**：`async_engine` fixture + `async_sessionmaker(engine)` 组出 factory 塞给 `DbChatMemory`——已验证可行（P6/P7 conftest 就这么用）。
- **CLI 未登录启动**：`auth_local.load()` 返回 None → 走 FileChatMemory → 不 touch DB → 不 init engine。零回归。
- **token 过期**：decode 抛 `TokenExpiredError` → catch → file fallback + 用户友好提示。不中断启动。
