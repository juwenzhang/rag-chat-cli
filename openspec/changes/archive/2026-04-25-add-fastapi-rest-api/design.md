# Design: FastAPI REST API Layer

## Context

AGENTS.md §5.1 给出了完整端点列表，§2 给出了目录约束：

```
api/
├── app.py
├── deps.py              # Change 5 已建
├── routers/
│   ├── auth.py
│   ├── chat.py
│   └── knowledge.py
├── schemas/
│   ├── auth.py          # Change 5 已建
│   ├── chat.py
│   ├── knowledge.py
│   └── common.py
└── middleware/
    ├── request_id.py
    ├── logging.py
    └── errors.py
```

## Goals / Non-Goals

**Goals**
- **无状态**：API 层不保存任何业务状态，全部委托 `core/` 服务。
- **可测试**：所有路由 100% 单测（httpx + ASGITransport）。
- **标准化响应**：成功返回领域对象，错误返回统一 `ErrorResponse`。
- **OpenAPI 严谨**：每个端点都有 response_model、status_code、tags、summary。

**Non-Goals**
- 不做 GraphQL、不做 HATEOAS。
- 不做 multipart 大文件上传的分片（document 上传本期只接受小于 10MB 的单 part）。

## Architecture

### `api/app.py`

```python
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or _settings
    init_engine(settings.db.database_url, echo=settings.db.echo_sql)

    app = FastAPI(
        title="rag-chat API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    # Middlewares —— 注意顺序：外层到内层
    app.add_middleware(CORSMiddleware, allow_origins=settings.app.cors_origins,
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(RequestIDMiddleware, header_name=settings.app.request_id_header)
    app.add_middleware(AccessLogMiddleware)

    # Exception handlers
    install_exception_handlers(app)

    # Routers
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(chat_router, prefix="/chat", tags=["chat"])
    app.include_router(knowledge_router, prefix="/knowledge", tags=["knowledge"])
    app.include_router(me_router, prefix="", tags=["me"])  # GET/PATCH /me

    @app.get("/health", tags=["meta"])
    async def health(): return {"status": "ok"}

    @app.on_event("shutdown")
    async def _shutdown(): await dispose_engine()

    return app
```

> 注：`@app.on_event` 官方已建议换 `lifespan`，本次直接用 `lifespan` async context manager。

### 路由骨架

#### `routers/auth.py`

```python
router = APIRouter()

@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: RegisterIn, svc: AuthService = Depends(get_auth_service)):
    return await svc.register(body.email, body.password, display_name=body.display_name)

@router.post("/login", response_model=TokenPair)
async def login(body: LoginIn, svc=Depends(get_auth_service)):
    return await svc.login(body.email, body.password)

@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshIn, svc=Depends(get_auth_service)):
    return await svc.refresh(body.refresh_token)

@router.post("/logout", status_code=204)
async def logout(body: RefreshIn, svc=Depends(get_auth_service)):
    await svc.logout(body.refresh_token)
```

#### `routers/me.py`

```python
router = APIRouter()

@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)): return user

@router.patch("/me", response_model=UserOut)
async def patch_me(body: UserPatchIn, user=Depends(get_current_user),
                   session: AsyncSession = Depends(get_session)):
    # 仅允许改 display_name
    if body.display_name is not None: user.display_name = body.display_name
    await session.commit(); await session.refresh(user); return user
```

#### `routers/chat.py`

```python
@router.post("/sessions", response_model=ChatSessionOut, status_code=201)
async def create_session(body: CreateSessionIn, user=Depends(get_current_user),
                         session=Depends(get_session)): ...

@router.get("/sessions", response_model=Page[ChatSessionOut])
async def list_sessions(page: int = 1, size: int = 20, user=Depends(get_current_user), ...): ...

@router.get("/sessions/{sid}/messages", response_model=Page[MessageOut])
async def list_messages(sid: UUID, page: int = 1, size: int = 50,
                        user=Depends(get_current_user), ...): ...

@router.post("/messages", response_model=MessageOut)
async def post_message(body: MessageIn, user=Depends(get_current_user),
                       svc: ChatService = Depends(get_chat_service)):
    """非流式：一次性拿完整回复。流式走 /chat/stream（Change 7）。"""
    full = await svc.generate_full(user.id, body.session_id, body.content, use_rag=body.use_rag)
    return full
```

#### `routers/knowledge.py`

```python
@router.post("/documents", response_model=DocumentOut, status_code=201)
async def upload_document(body: DocumentIn, user=Depends(get_current_user), ...):
    """本期只接受 {source, title, content} JSON；multipart 留给 ingest CLI。"""

@router.post("/documents:reindex", status_code=202)
async def reindex(user=Depends(get_current_user)):
    """返回 202，实际异步任务在 Change 8 (workers) 接入；本期同步跑或抛 501。"""

@router.get("/search", response_model=list[SearchHitOut])
async def search(q: str, top_k: int = 4, user=Depends(get_current_user)):
    """本期无向量召回实现 → 返回空列表并记日志；Change 9 实装。"""
    return []
```

### Schemas

`api/schemas/common.py`：

```python
T = TypeVar("T")

class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    size: int
    total: int

class ErrorResponse(BaseModel):
    code: str            # e.g. "INVALID_CREDENTIALS"
    message: str
    request_id: str | None = None
    details: dict | None = None

class OkResponse(BaseModel):
    ok: bool = True
```

### 中间件

#### `middleware/request_id.py`

```python
_REQ_ID: ContextVar[str] = ContextVar("request_id", default="")

class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, header_name: str): ...
    async def dispatch(self, request, call_next):
        rid = request.headers.get(self.header_name) or uuid4().hex
        token = _REQ_ID.set(rid)
        try:
            resp = await call_next(request)
            resp.headers[self.header_name] = rid
            return resp
        finally: _REQ_ID.reset(token)

def current_request_id() -> str: return _REQ_ID.get()
```

#### `middleware/logging.py`

- 记录 `method path status duration_ms user_id? request_id`。
- 结构化：走 `structlog` 或 `logging` + JsonFormatter。
- 跳过 `/health`、`/openapi.json`、`/docs`。

#### `middleware/errors.py` 的映射

| 异常 | HTTP | code |
|---|---|---|
| `InvalidCredentialsError` | 401 | `INVALID_CREDENTIALS` |
| `EmailAlreadyExistsError` | 409 | `EMAIL_EXISTS` |
| `TokenExpiredError` | 401 | `TOKEN_EXPIRED` |
| `TokenInvalidError` | 401 | `TOKEN_INVALID` |
| `TokenReuseError` | 401 | `TOKEN_REUSE_DETECTED` |
| `UserNotActiveError` | 403 | `USER_INACTIVE` |
| `pydantic.ValidationError` | 422 | `VALIDATION_ERROR` |
| `KeyError`/`LookupError` | 404 | `NOT_FOUND` |
| 兜底 `Exception` | 500 | `INTERNAL` |

每个 handler 返回 `ErrorResponse`，并把 `request_id` 注入。

### `app/cli.py` 的 `serve` 实装

```python
case "serve":
    import uvicorn
    uvicorn.run(
        "api.app:create_app", factory=True,
        host=ns.host, port=ns.port, reload=ns.reload,
        log_level=settings.app.log_level.lower(),
    )
```

`serve` 子命令支持 `--host 0.0.0.0 --port 8000 --reload`。

### OpenAPI dump

- `scripts/dump_openapi.py`：`from api.app import create_app; json.dump(create_app().openapi(), open("docs/openapi.json","w"))`。
- `Makefile` 的 `openapi` target 在 Change 11 串起来。

## Alternatives Considered

- **Starlette only**：过于底层，失去 OpenAPI 自动化；AGENTS.md §1 已定 FastAPI。
- **Litestar**：性能好，但 ecosystem 不如 FastAPI，团队学习成本高。

## Risks & Mitigations

- **风险**：`create_app()` 多次调用会多次 `init_engine` 导致池泄漏。
  **缓解**：`init_engine` 内部幂等，二次调用直接返回已存在 engine。
- **风险**：CORS 过宽导致安全问题。
  **缓解**：`settings.app.cors_origins: list[str]`，prod 强制非空；dev 允许 `["*"]`。
- **风险**：exception handler 吞掉 stacktrace。
  **缓解**：500 路径必须 `logger.exception(...)`；非 500 只记 warn。

## Testing Strategy

- 单元/集成（同文件内用 ASGITransport）：
  - `tests/api/test_health.py`：`GET /health == 200 {"status":"ok"}`。
  - `tests/api/test_auth_flow.py`：register → login → /me → refresh → logout 全链路。
  - `tests/api/test_chat_routes.py`：
    - 未带 token 访问 `/chat/sessions` → 401。
    - 登录后创建 session、发消息、拉 messages 列表分页正确。
  - `tests/api/test_knowledge_routes.py`：上传 + search 返回空。
  - `tests/api/test_errors.py`：故意抛每种异常，断言响应 `code` 与 HTTP status。
- 基线：
  - 启动 `uvicorn api.app:create_app --factory --port 8001`，`curl http://localhost:8001/docs` 200。
  - `scripts/dump_openapi.py` 产物非空且含所有 tag。
