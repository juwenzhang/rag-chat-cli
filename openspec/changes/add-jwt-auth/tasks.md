# Tasks: Add JWT Authentication

## 1. 依赖

- [ ] 1.1 `pyproject.toml` 新增：`python-jose[cryptography]>=3.3`、`passlib[bcrypt]>=1.7.4`、`email-validator>=2.1`（pydantic EmailStr 用）。
- [ ] 1.2 `uv sync` 成功。
- [ ] 1.3 验证 `python -c "from jose import jwt; from passlib.context import CryptContext; print('ok')"`。

## 2. Settings 扩展

- [ ] 2.1 `settings.auth` 补字段：`bcrypt_rounds: int = 12`、`refresh_reuse_detection: bool = True`。
- [ ] 2.2 `.env.example` 补 `AUTH__BCRYPT_ROUNDS=12`。
- [ ] 2.3 prod 模式下 `AUTH__JWT_SECRET` 缺失必须 raise（Change 1 已实现，验证通过）。

## 3. `core/auth/password.py`

- [ ] 3.1 初始化 `CryptContext(schemes=["bcrypt"])`。
- [ ] 3.2 `hash_password(plain) -> str`、`verify_password(plain, hashed) -> bool`。
- [ ] 3.3 单测：round-trip + 错密码 False。

## 4. `core/auth/tokens.py`

- [ ] 4.1 `TokenPayload` dataclass（frozen）。
- [ ] 4.2 `create_access_token(user_id, *, ttl_min=None) -> str`。
- [ ] 4.3 `create_refresh_token(user_id, *, ttl_day=None) -> tuple[str, str]` 返回 (jwt, jti)。
- [ ] 4.4 `decode_token(token, *, expected_type)`：
  - 签名错/篡改 → `TokenInvalidError`。
  - 过期 → `TokenExpiredError`。
  - 类型不匹配（access 当 refresh 用）→ `TokenInvalidError`。
- [ ] 4.5 单测：三种异常路径 + 正常路径。

## 5. `core/auth/errors.py`

- [ ] 5.1 实现 `AuthError` 及 6 个子类（见 design）。
- [ ] 5.2 所有子类必须可被 `isinstance(e, AuthError)` 命中。

## 6. `core/auth/service.py`

- [ ] 6.1 `AuthService.__init__(session_factory)`。
- [ ] 6.2 `register(email, password, display_name=None) -> User`：
  - email 已存在 → `EmailAlreadyExistsError`。
  - 写 `users` 表，`hashed_password = hash_password(password)`。
- [ ] 6.3 `login(email, password) -> TokenPair`：
  - 找不到用户或密码错 → `InvalidCredentialsError`（统一错误信息避免枚举攻击）。
  - 签发 access + refresh；refresh 的 jti 落 `refresh_tokens` 表。
- [ ] 6.4 `refresh(refresh_token) -> TokenPair`：
  - 解码、查 jti 行。
  - 若 `revoked_at` 非空 → 吊销该 user 全部未过期 refresh（`UPDATE ... WHERE user_id=:u AND revoked_at IS NULL`），raise `TokenReuseError`。
  - 若未吊销：`UPDATE ... RETURNING` 标 revoked；签新 access + refresh；新 jti 落表。
- [ ] 6.5 `logout(refresh_token)`：标 revoked。
- [ ] 6.6 `get_user_by_access(access_token) -> User`。

## 7. `api/schemas/auth.py`

- [ ] 7.1 新建 `api/__init__.py`、`api/schemas/__init__.py`。
- [ ] 7.2 `RegisterIn(email: EmailStr, password: constr(min_length=8), display_name: str | None)`。
- [ ] 7.3 `LoginIn(email: EmailStr, password: str)`。
- [ ] 7.4 `TokenPair`（含时间字段，ISO 格式）。
- [ ] 7.5 `UserOut(id, email, display_name, is_active, created_at)`（`model_config = ConfigDict(from_attributes=True)`）。

## 8. `api/deps.py`

- [ ] 8.1 实现 `get_current_user`（见 design）。
- [ ] 8.2 实现 `get_auth_service(session=Depends(get_session)) -> AuthService`。
- [ ] 8.3 注意：本次**不注册路由**，只提供函数，Change 6 会接入。

## 9. CLI 本地 token 存储

- [ ] 9.1 `app/auth_local.py`：`save / load / clear / import_from_string`。
- [ ] 9.2 `chmod(0o600)`（Windows 跳过）。
- [ ] 9.3 单测用 `monkeypatch.setenv("HOME", tmp_path)` 验证路径与权限。

## 10. CLI 斜杠命令实装

- [ ] 10.1 `/login`：交互输入邮箱/密码 → `AuthService.login` → `save`。
- [ ] 10.2 `/logout`：`load` → `AuthService.logout(refresh)` → `clear`。
- [ ] 10.3 `/whoami`：`load` + decode access，展示 email（过期时提示 "session expired"）。
- [ ] 10.4 失败/异常路径走 `view.error(code, message)`。

## 11. 测试

- [ ] 11.1 `tests/unit/core/auth/test_password.py`、`test_tokens.py`、`test_service.py`（DB 用 SQLite in-memory + alembic upgrade）。
- [ ] 11.2 `tests/unit/app/test_auth_local.py`。
- [ ] 11.3 `tests/integration/auth/test_cli_login_flow.py`。
- [ ] 11.4 `uv run pytest -q -k auth` 全绿。

## 12. 质量与文档

- [ ] 12.1 `ruff check core/auth/ api/ app/auth_local.py` 无错。
- [ ] 12.2 `mypy --strict core/auth/` 无错。
- [ ] 12.3 `docs/API.md` 先加占位："auth endpoints 见 Change `add-fastapi-rest-api`"。
- [ ] 12.4 README 补 `openssl rand -hex 32` 生成 `JWT_SECRET` 的说明。
- [ ] 12.5 AGENTS.md §19 Change Log 追加 "JWT auth + CLI token store"。

## 13. 冒烟

- [ ] 13.1 `python main.py chat` → `/login` 走通，`~/.config/rag-chat/token.json` 存在且 0600。
- [ ] 13.2 `/whoami` 显示正确邮箱。
- [ ] 13.3 `/logout` 后 `token.json` 被删除。
- [ ] 13.4 `python -c "from core.auth.tokens import create_access_token, decode_token; ..."` round-trip 通过。
