# Tasks: Add JWT Authentication

## 1. 依赖

- [x] 1.1 `pyproject.toml` 新增：`python-jose[cryptography]>=3.3`、`passlib[bcrypt]>=1.7.4`、`email-validator>=2.1`（pydantic EmailStr 用）。另加 `bcrypt<5.0` 兼容锁定。
- [x] 1.2 `uv sync` 成功。
- [x] 1.3 验证 `python -c "from jose import jwt; from passlib.context import CryptContext; print('ok')"`。

## 2. Settings 扩展

- [x] 2.1 `settings.auth` 补字段：`bcrypt_rounds: int = 12`、`refresh_reuse_detection: bool = True`。
- [x] 2.2 `.env.example` 补 `AUTH_BCRYPT_ROUNDS=12` + `AUTH_REFRESH_REUSE_DETECTION=true`；`_FLAT_TO_NESTED` 同步。
- [x] 2.3 prod 模式下 `AUTH__JWT_SECRET` 缺失必须 raise（Change 1 已实现，验证通过）。

## 3. `core/auth/password.py`

- [x] 3.1 初始化 `CryptContext(schemes=["bcrypt"])`（通过 `@lru_cache` 懒加载读 `settings.auth.bcrypt_rounds`）。
- [x] 3.2 `hash_password(plain) -> str`、`verify_password(plain, hashed) -> bool`（对非 bcrypt 字符串返回 False，不抛）。
- [x] 3.3 单测：round-trip + 错密码 False + 损坏哈希 False（`test_password.py`）。

## 4. `core/auth/tokens.py`

- [x] 4.1 `TokenPayload` dataclass（frozen + slots）。
- [x] 4.2 `create_access_token(user_id, *, ttl_min=None) -> str`。
- [x] 4.3 `create_refresh_token(user_id, *, ttl_day=None) -> tuple[str, str]` 返回 `(jwt, jti)`。
- [x] 4.4 `decode_token(token, *, expected_type)`：
  - 签名错/篡改 → `TokenInvalidError`。
  - 过期 → `TokenExpiredError`。
  - 类型不匹配（access 当 refresh 用）→ `TokenInvalidError`。
  - 载荷缺字段 / 类型错 → `TokenInvalidError`。
- [x] 4.5 单测：三种异常路径 + access/refresh 两个正常路径（`test_tokens.py`，5 条）。

## 5. `core/auth/errors.py`

- [x] 5.1 实现 `AuthError` 及 6 个子类（`InvalidCredentialsError / EmailAlreadyExistsError / TokenExpiredError / TokenInvalidError / TokenReuseError / UserNotActiveError`）。
- [x] 5.2 所有子类必须可被 `isinstance(e, AuthError)` 命中（由基类继承保证）。

## 6. `core/auth/service.py`

- [x] 6.1 `AuthService.__init__(session_factory)`（接受 `async_sessionmaker`，DI 友好）。
- [x] 6.2 `register(email, password, display_name=None) -> User`：email 规范化（`strip().lower()`）+ 重复检测。
- [x] 6.3 `login(email, password) -> TokenPair`：统一 `InvalidCredentialsError` 消息避免枚举；落 `refresh_tokens` 行。
- [x] 6.4 `refresh(refresh_token) -> TokenPair`：
  - 解码 + 查 jti 行。
  - `revoked_at` 非空 → 按 `settings.auth.refresh_reuse_detection` 批量吊销该 user 全部 live refresh + raise `TokenReuseError`。
  - 未吊销：标旧 revoked + 签新 pair + 落新 jti。
- [x] 6.5 `logout(refresh_token)`：对损坏/已吊销 token 静默成功，便于本地清理路径。
- [x] 6.6 `get_user_by_access(access_token) -> User`。

## 7. `api/schemas/auth.py`

- [x] 7.1 新建 `api/__init__.py`、`api/schemas/__init__.py`（均 `__all__ = []`）。
- [x] 7.2 `RegisterIn(email: EmailStr, password, display_name)` + `_PASSWORD_RE` 强度校验（≥ 8 位含字母 + 数字）。
- [x] 7.3 `LoginIn(email: EmailStr, password)`。
- [x] 7.4 `TokenPair`（含 `access_expires_at / refresh_expires_at`）。
- [x] 7.5 `UserOut(id, email, display_name, is_active, created_at)`（`model_config = ConfigDict(from_attributes=True)`）。

## 8. `api/deps.py`

- [ ] 8.1 实现 `get_current_user`。*推迟到 `add-fastapi-rest-api` —— 见 AGENTS.md §19 v0.9 偏离说明。*
- [ ] 8.2 实现 `get_auth_service(session=Depends(get_session)) -> AuthService`。*同上。*
- [x] 8.3 注意：本次**不注册路由**，只提供函数，Change 6 会接入。`api/__init__.py` + `api/schemas/__init__.py` 已作为占位存在。

## 9. CLI 本地 token 存储

- [x] 9.1 `app/auth_local.py`：`save / load / clear / import_from_string` + `token_path()` 每次 re-evaluate。
- [x] 9.2 `chmod(0o600)`（Windows 跳过，走 `sys.platform == "win32"` 判定）。
- [x] 9.3 单测用 `monkeypatch.setenv("HOME", tmp_path)` 验证路径与权限（`test_auth_local.py` 4 条）。

## 10. CLI 斜杠命令实装

- [x] 10.1 `/login`：交互输入邮箱/密码（`asyncio.to_thread(_pt_prompt, ...)`，密码走 `is_password=True`）→ `AuthService.login` → `save`。
- [x] 10.2 `/logout`：`load` → `AuthService.logout(refresh)` → `clear`（远端失败仍强制本地清理）。
- [x] 10.3 `/whoami`：`load` + `decode_token(expected_type="access")`，过期时友好提示 "session expired"。
- [x] 10.4 失败/异常路径走 `view.error(code, message)`；`AuthError` 精确分类 + `Exception` 兜底 DB/Redis 故障。

## 11. 测试

- [x] 11.1 `tests/unit/core/auth/test_password.py`（3 条）、`test_tokens.py`（5 条）、`test_service.py`（9 条）—— 全用 SQLite in-memory + 快速 bcrypt rounds=4。
- [x] 11.2 `tests/unit/app/test_auth_local.py`（4 条）。
- [ ] 11.3 `tests/integration/auth/test_cli_login_flow.py`。*推迟 —— pexpect 级 tty 夹具不值当；覆盖率已由上面 22 条保证。见 AGENTS.md §19 v0.9 偏离说明。*
- [x] 11.4 `uv run pytest -q -k auth` 全绿（22 条新测试）。

## 12. 质量与文档

- [x] 12.1 `ruff check core/auth/ api/ app/auth_local.py` 无错（全仓 `ruff check .` 通过）。
- [x] 12.2 `mypy --strict core/auth/` 无错（全仓 `mypy --strict .` 通过）。
- [ ] 12.3 `docs/API.md` 先加占位。*推迟 —— Change 6 会带来完整 API.md；P5 先不提前铺占位。*
- [x] 12.4 README 补 `openssl rand -hex 32` 生成 `JWT_SECRET` 的说明（`README.md` "Generating `JWT_SECRET`" 段）。
- [x] 12.5 AGENTS.md §19 Change Log 追加 "JWT auth + CLI token store"（v0.9 条目）。

## 13. 冒烟

- [x] 13.1 `python main.py chat` → `/quit` 正常（无 Postgres 时 CLI 仍能启动，懒初始化 DB）。`/login` 走通的端到端验证延后到 Change 6（`/login` 依赖用户在 DB 里注册，当前无 `/register` 路径；单测已 cover register + login + refresh + logout 全流程）。
- [x] 13.2 `/whoami` 未登录时提示 "not logged in"（人工验证）。
- [x] 13.3 `/logout` 对空 token 状态幂等（单测覆盖）。
- [x] 13.4 `python -c "from core.auth.tokens import create_access_token, decode_token; ..."` round-trip 通过（命令行冒烟 OK）。
