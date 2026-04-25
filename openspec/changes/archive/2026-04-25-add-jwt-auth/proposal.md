# Proposal: Add JWT Authentication (邮箱 + 密码)

## Why

AGENTS.md §6 明确：

> 认证：JWT（access + refresh），`python-jose[cryptography]` + `passlib[bcrypt]`；支持邮箱 + 密码注册/登录。
> CLI：本地持久化 token 到 `~/.config/rag-chat/token.json`（0600）。

§15 P4 阶段强依赖本次 change：FastAPI 的所有业务路由都要 `Depends(get_current_user)`；Change 14（web 登录→Token 一键复制给 CLI）亦强依赖。

当前项目**没有任何鉴权概念**，连 User 表都没有（Change 4 刚建）。本次在 DB 基础上叠加：注册/登录/刷新/登出 + CLI 本地 token 管理。

## What Changes

- 新增 `core/auth/` 模块：
  - `core/auth/password.py` — `hash_password / verify_password`（bcrypt）。
  - `core/auth/tokens.py` — `create_access_token / create_refresh_token / decode_token`；refresh token 写入 DB 的 `refresh_tokens.jti`，支持主动 revoke。
  - `core/auth/service.py` — `AuthService`：`register / login / refresh / logout / get_user_by_token`。
- 新增 `api/deps.py` 的 `get_current_user`（FastAPI 依赖，本次只建函数，Change 6 真正接入路由）。
- CLI 端新增 `app/auth_local.py`：
  - `save_token(token_pair, path=~/.config/rag-chat/token.json, mode=0o600)`。
  - `load_token() -> TokenPair | None`。
  - `clear_token()`。
- `app/chat_app.py` 的 `/login` 斜杠命令**真正实装**：
  - 走 `POST /auth/login` 或直接调 `AuthService.login`（本阶段 CLI 直连 core，Web 上线后再走 HTTP）。
  - 成功后 `save_token`。
- 新增 schemas：`api/schemas/auth.py` 的 `RegisterIn / LoginIn / TokenPair / UserOut`（Change 6 会复用）。
- Settings 补 `auth.bcrypt_rounds: int = 12`、`auth.refresh_reuse_detection: bool = True`。

## Non-goals

- 不接入 OAuth / SSO。
- 不做 RBAC / 权限粒度（本次所有用户对等）。
- 不做 2FA / MFA。
- 不做 email 验证发送（`is_active` 默认为 True）。
- 不写 FastAPI 的 `/auth/*` 路由（Change 6 做）。

## Impact

- **新增**：`core/auth/__init__.py`、`password.py`、`tokens.py`、`service.py`；`api/deps.py`；`api/schemas/__init__.py`、`api/schemas/auth.py`；`app/auth_local.py`。
- **修改**：`settings.py`（补 2 个字段）、`app/chat_app.py`（`/login /logout` 实装）、`.env.example`。
- **依赖**：`python-jose[cryptography]>=3.3`、`passlib[bcrypt]>=1.7.4`、`pydantic[email]>=2.7`。
- **风险**：中。涉及密码散列、token 秘钥管理；必须有单测保护；`.env` 的 `AUTH__JWT_SECRET` 在 prod 必填（Change 1 已埋点）。
- **回退方式**：`git revert`；DB 中 `refresh_tokens` 表保留，下一次 migration 或手工清理。
