# Design: JWT Authentication

## Context

AGENTS.md §6 与 §14 的约束：
- access / refresh 双 token；refresh token 落 DB 表 `refresh_tokens` 支持主动吊销。
- `passlib[bcrypt]` 散列密码，`python-jose` 签名/校验。
- CLI 侧 token 文件 `~/.config/rag-chat/token.json` 权限 0600。
- 所有 token 载荷必须含：`sub`（user_id）、`jti`、`type`（`"access"|"refresh"`）、`iat`、`exp`。

## Goals / Non-Goals

**Goals**
- core/auth 层**不依赖** FastAPI（可被 CLI 直连、API 直连，两路复用）。
- refresh token 支持 rotation + reuse detection（一次用掉即作废；旧 refresh 再次出现视作被盗并吊销整个 session）。
- access token 无状态（不查 DB）；refresh token 必须查 DB。
- 对外抛的错误用 `AuthError` 子类，API 层再映射到 HTTP 状态。

**Non-Goals**
- 不做 OAuth2 Authorization Code flow。
- 不把 token 签入 URL / query string。

## Architecture

```
core/auth/
├── __init__.py
├── errors.py      # AuthError 基类 + 具体子类
├── password.py    # bcrypt 封装
├── tokens.py      # JWT 编解码、jti 生成
└── service.py     # AuthService 业务编排
```

### `password.py`

```python
_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto",
                    bcrypt__rounds=settings.auth.bcrypt_rounds)

def hash_password(plain: str) -> str: return _ctx.hash(plain)
def verify_password(plain: str, hashed: str) -> bool: return _ctx.verify(plain, hashed)
```

### `tokens.py`

```python
@dataclass(frozen=True)
class TokenPayload:
    sub: str            # user_id (UUID str)
    jti: str            # uuid4
    type: Literal["access", "refresh"]
    iat: int
    exp: int

def create_access_token(user_id: UUID, *, ttl_min: int | None = None) -> str: ...
def create_refresh_token(user_id: UUID, *, ttl_day: int | None = None) -> tuple[str, str]:
    """Returns (jwt_string, jti). 调用方负责把 jti 落 DB。"""
def decode_token(token: str, *, expected_type: Literal["access","refresh"]) -> TokenPayload: ...
```

所有 JWT 使用 `settings.auth.jwt_secret` + `HS256`（§6）。

### `service.py`

```python
class AuthService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._sf = session_factory

    async def register(self, email: str, password: str, *, display_name: str | None = None) -> User: ...
    async def login(self, email: str, password: str) -> TokenPair: ...
    async def refresh(self, refresh_token: str) -> TokenPair:
        """Rotation: 旧 refresh 标 revoked_at，新 refresh 落 DB。
        如果入参 refresh 对应的 jti.revoked_at 非空，则认为是重放攻击，
        吊销该用户全部未过期 refresh token 并抛 TokenReuseError。"""
    async def logout(self, refresh_token: str) -> None:
        """仅作废这一条 refresh。access token 仍剩余其 TTL（本期接受此风险）。"""
    async def get_user_by_access(self, access_token: str) -> User: ...
```

`TokenPair` schema：

```python
class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    access_expires_at: datetime
    refresh_expires_at: datetime
```

### 错误体系

```python
class AuthError(Exception): ...
class InvalidCredentialsError(AuthError): ...
class EmailAlreadyExistsError(AuthError): ...
class TokenExpiredError(AuthError): ...
class TokenInvalidError(AuthError): ...
class TokenReuseError(AuthError): ...
class UserNotActiveError(AuthError): ...
```

Change 6 的 API 层将在 exception handler 中把这些映射为 401/409/400。

### `api/deps.py`（只定义函数，不挂路由）

```python
bearer = HTTPBearer(auto_error=False)

async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not creds: raise HTTPException(401, "missing bearer")
    try:
        payload = decode_token(creds.credentials, expected_type="access")
    except TokenExpiredError:
        raise HTTPException(401, "token expired")
    except TokenInvalidError:
        raise HTTPException(401, "invalid token")
    user = await session.get(User, UUID(payload.sub))
    if not user or not user.is_active:
        raise HTTPException(401, "user inactive")
    return user
```

### CLI 本地 token 存储

`app/auth_local.py`：

```python
TOKEN_PATH = Path("~/.config/rag-chat/token.json").expanduser()

def save(pair: TokenPair) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(pair.model_dump_json(indent=2))
    TOKEN_PATH.chmod(0o600)

def load() -> TokenPair | None:
    if not TOKEN_PATH.exists(): return None
    return TokenPair.model_validate_json(TOKEN_PATH.read_text())

def clear() -> None:
    if TOKEN_PATH.exists(): TOKEN_PATH.unlink()

def import_from_string(encoded: str) -> TokenPair:
    """支持 Web 端复制的 'rag://token?a=...&r=...' 或纯 JSON，两种都解析。"""
```

### CLI 登录命令实装

`app/chat_app.py` `/login` handler：

1. 交互式 `prompt_toolkit` 读 email + 密码（密码用 `is_password=True`）。
2. 直连 `AuthService.login(email, pwd)` 拿 `TokenPair`。
3. `auth_local.save(pair)`，`view.system_notice("logged in as <email>")`。
4. 失败打印红字错误（`view.error(code, msg)`）。

`/logout`：

1. `auth_local.load()` → 若有 refresh，调 `AuthService.logout(refresh)`。
2. `auth_local.clear()`。

Change 14 会增加 `/login-with-token <token_string>` 用于 Web→CLI 复制流。

## Alternatives Considered

- **paseto**：安全但生态不如 JWT 广泛；AGENTS.md §6 已定 JWT。
- **sessions in cookie**：Web 端方便，但 CLI 不好用；统一 JWT bearer。
- **argon2 代替 bcrypt**：更安全，AGENTS.md §6 选 bcrypt，尊重现有约束。

## Risks & Mitigations

- **风险**：`JWT_SECRET` 泄漏 = 全盘失守。
  **缓解**：Change 1 已约定 prod 必填强随机；README 说明 `openssl rand -hex 32`；CI 必须设置该变量。
- **风险**：refresh rotation 并发场景下同一 jti 被两端同时刷新。
  **缓解**：DB 层 `UPDATE refresh_tokens SET revoked_at=now() WHERE jti=:j AND revoked_at IS NULL RETURNING ...`，只有 RETURNING 有行的才能继续签新 token；其他失败视为 reuse。
- **风险**：CLI token 文件权限在 Windows 上 0600 不生效。
  **缓解**：Windows 下跳过 `chmod`，并在文件头加一行提示注释"请勿共享"。

## Testing Strategy

- 单元：
  - `tests/unit/core/auth/test_password.py`：hash + verify 正常；wrong password 返回 False。
  - `tests/unit/core/auth/test_tokens.py`：编解码 round-trip；篡改 header 报 `TokenInvalidError`；过期 `TokenExpiredError`。
  - `tests/unit/core/auth/test_service.py`：
    - 注册同邮箱第二次 → `EmailAlreadyExistsError`。
    - 登录密码错 → `InvalidCredentialsError`。
    - refresh rotation 正常流 + 重放 → `TokenReuseError` 且全部 refresh 被吊销。
- 集成：
  - `tests/integration/auth/test_cli_login_flow.py`：临时 HOME，`/login` 流程后 `token.json` 存在且 0600（Linux/macOS）。
