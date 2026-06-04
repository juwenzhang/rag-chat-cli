# Multi-Client Authentication Design

> Status: Phase 1 implemented; Phase 2 / 3 planned.

## 0. 背景

后端 `api/` 起步时只面向单一 Web 客户端（`websites/` 下的 Next.js 应用）：登录是 cookie-less 的 JWT bearer，CORS 用 `APP_CORS_ORIGINS` 严格白名单。当我们把 Ink 终端客户端 (`clients/tui/`) 接进来之后，立刻暴露了三个问题：

1. **CDN / 反向代理（如 Hugging Face Space）会对非浏览器请求做边缘拦截**——CLI 的 `fetch` 没有 `Origin` header、UA 不像浏览器，常被识别为爬虫直接拒绝，但同一份代码本机直连 FastAPI 又是可以通的。
2. **Web 与 CLI 共用一套 token**——意味着浏览器里被 XSS 偷到的 access token 可以被攻击者拿来在 CLI 里跑 `/kb sync` 这类破坏性命令。爆炸半径不可控。
3. **未来还会有 mobile / IDE 插件 / 第三方集成**，再每来一个客户端就给 CORS 白名单加一行，本质是把"客户端识别"压在网络层做，不可持续。

**核心错误是把"客户端类型"作为一个 _network-level_ 概念在处理**——更稳健的模型是把它显式建模成 _application-level_ 一等公民：每种客户端是一个独立的 OAuth Client，有自己的 `client_id`、scope、TTL、撤销策略和审计链路。这是 OAuth 2.1 / RFC 8628（Device Authorization Grant）已经替整个行业回答过的问题。

## 1. 目标 & 非目标

**目标**

- 把 `Web` 与 `CLI` 在认证体系里**显式区分**，便于差异化策略（TTL、scope、撤销面板、安全告警）。
- 让 CLI 在 HF Space 这类强反代环境下能稳定跑通，**不依赖反代规则**。
- 同一套用户身份模型（`User`）下，未来加入 mobile / 插件 / 第三方时**零结构变更**。
- 渐进交付，分三阶段，每阶段都能独立合并，避免一次性大改动。

**非目标**

- 不引入第三方 IdP（Keycloak / Auth0）——内置即可。
- 不重写现有 `/auth/login`、`/auth/refresh` 业务逻辑，只在外围加分流。
- 不立即落地 DPoP / mTLS（Phase 4+ 再考虑）。

## 2. 整体分层

```text
                ┌─────────────────────────────────────────────────────┐
                │                FastAPI app                          │
                │                                                     │
   Browser  ──► │ /v1/web/*    CookieAuthMiddleware + CSRF + Origin   │
                │                                                     │
   CLI      ──► │ /v1/*        BearerAuthMiddleware + X-Client-Id     │
                │                                                     │
   Worker   ──► │ /internal/*  mTLS / IP allowlist                    │
                └─────────────────────────────────────────────────────┘
```

三层认证**入口分离**而不是 `if request.headers.get("user-agent").startswith(...)` 这种内联分支。理由：

- 反向代理 / WAF / 速率限制规则可以**按路径前缀**单独配置，CLI 路径 `/v1/*` 可以独立开放无 Origin 约束。
- 出问题时 audit log 用 path prefix 一眼分流。
- 未来上 mTLS、零信任 mesh 也只动 `/internal/*`，不影响业务路径。

## 3. 关键决策

### 3.1 客户端身份是一等公民（`OAuthClient` 表）

引入一张新表（Phase 2 落地）：

| 字段 | 含义 |
|---|---|
| `id` (uuid) | 主键 |
| `name` | `lhx-rag-cli` / `lhx-rag-web` / `lhx-rag-mobile-ios` … |
| `type` | `public` (CLI/SPA, 不存 secret) / `confidential` (server-side, 存 hashed secret) |
| `redirect_uris` | 仅授权码流程使用 |
| `allowed_scopes` | `chat:read,chat:write,kb:read,...` |
| `pkce_required` | public client 强制 true |
| `access_token_ttl_sec` | 客户端粒度 TTL（CLI 默认 30 min，web 5 min） |
| `refresh_token_ttl_sec` | CLI 30 天，web 7 天 |
| `created_by_user_id` | 审计 |
| `created_at` / `revoked_at` | 时间戳 + 撤销 |

**为什么不只用全局 secret**：未来加 mobile / 插件 / 三方时不用再开第二套体系。OAuth 客户端表是"未来不后悔"的最小代价。

### 3.2 CLI 用 Device Authorization Grant（RFC 8628）

CLI 不该直接收用户密码——这是设计的**安全核心**。

```text
┌──────────────┐                ┌──────────────┐                ┌──────────────┐
│   lhx-rag    │                │  FastAPI     │                │  Browser     │
│   (CLI)      │                │  /oauth/*    │                │  (any)       │
└──────────────┘                └──────────────┘                └──────────────┘
       │                                │                                │
       │ POST /oauth/device/authorize   │                                │
       │ {client_id, scope}             │                                │
       │───────────────────────────────►│                                │
       │ {device_code, user_code,       │                                │
       │  verification_uri,             │                                │
       │  interval=5, expires_in=600}   │                                │
       │◄───────────────────────────────│                                │
       │                                │                                │
       │ 显示给用户:                     │                                │
       │  打开 URL 输入码 ABCD                                            │
       │                                │                                │
       │                                │   GET /device?user_code=ABCD   │
       │                                │◄───────────────────────────────│
       │                                │   web 内确认（cookie 登录）     │
       │                                │                                │
       │ 同时 CLI 轮询:                  │                                │
       │ POST /oauth/token              │                                │
       │ grant=device_code              │                                │
       │ device_code=...                │                                │
       │───────────────────────────────►│                                │
       │  pending / slow_down / token   │                                │
       │◄───────────────────────────────│                                │
```

CLI **永远拿不到密码**，密码只在浏览器里输给 Web。CLI 拿到的 token 是专属于 CLI `client_id` 的、可独立撤销的。

### 3.3 JWT 中显式带 `aud` (client_id) + `scope`

```json
{
  "sub": "user_uuid",
  "iss": "lhx-rag",
  "aud": "lhx-rag-cli",
  "scope": "chat:write kb:read",
  "iat": ..., "exp": ...,
  "jti": "..."
}
```

中间件强制校验 `aud == 期望的 client_id`，**Web 的 token 复制到 CLI 用不了，反之亦然**。

### 3.4 中间件分层（FastAPI）

```python
# api/security/clients.py
class WebClientGuard:
    """Cookie auth + CSRF + Origin allowlist."""
    async def __call__(self, request: Request) -> User: ...

class BearerClientGuard:
    """Authorization: Bearer + X-Client-Id + scope check."""
    def __init__(self, scopes: set[str]): ...
    async def __call__(self, request: Request) -> User: ...

# api/routers/chat.py (web)
@router.post(
    "/v1/web/chat/stream",
    dependencies=[Depends(WebClientGuard())],
)

# api/routers/chat_cli.py
@router.post(
    "/v1/chat/stream",
    dependencies=[Depends(BearerClientGuard(scopes={"chat:write"}))],
)
```

两套路由前缀，两套依赖，**反代/CDN/WAF 规则按路径分别挂**。

### 3.5 CLI 侧加固

- **token 文件 0600 权限**（已经做了）。
- **OS keyring 优先**：macOS Keychain / Windows Credential Vault / libsecret，回退到磁盘文件。可以加 `keytar` 或 `@napi-rs/keyring`（Phase 3+）。
- **设备指纹**：CLI 启动时生成 `device_id = hash(machine-id + os-user)`，登录时上报，server 把 token 与 device_id 绑定。Web 可以列出"已授权设备"并撤销。
- **离线 grace period**：access token 过期但还在 grace 时段（比如 1 小时）允许 stale 用，离线场景更友好。
- **请求签名（可选高阶）**：Phase 4+ 考虑 DPoP（RFC 9449）——public client 没 secret，用一次性 device-bound key。

### 3.6 Scope 粒度

```text
chat:read       chat:write       chat:stream
kb:read         kb:write         kb:admin
session:read    session:write    session:delete
provider:read   provider:write
auth:profile    auth:revoke
admin:*         (web only — CLI 永不发 admin scope)
```

CLI 申请时按命令推断最小 scope；Web 默认申请最广 scope。**即便 CLI token 泄漏，最坏只能聊天，不能改 provider 或删 KB**。

### 3.7 撤销 & 审计

- 每个 access token 写 `jti`，refresh token 写 `id`。
- Redis 放 `revoked:{jti}` set，TTL = token 剩余生命。
- `/me/sessions` API 列出本人所有 device，每条带 `client_name + last_used_at + ip + revoke_url`。
- 审计日志（`access_log`）增加 `client_id` 列，CLI 调用全部可追溯。

## 4. 渐进落地路径

### Phase 1：路径前缀 + 客户端 header（今天合并）

**目标**：解决 CLI 在反代后被拦的问题，零数据库变更，不动现有 web 行为。

1. 后端：`api/app.py` 把所有现有 router 同时挂到 `/v1/` 前缀下；保留根路径用作 web 流量（向后兼容现有 websites 调用）。
2. 后端：新增 `api/middleware/client_id.py`，对 `/v1/*` 路径要求 `X-Client-Id` header（白名单 `lhx-rag-cli`、`lhx-rag-web`），缺失 → `400 missing X-Client-Id`，不在白名单 → `400 unknown client`。Web 路径不要求。
3. 后端：`/v1/*` CORS 单独宽松（`allow_origins=["*"]`），因为 bearer-only 不依赖 cookie，没有跨站凭证攻击面；根路径 CORS 维持原 `APP_CORS_ORIGINS` 严格模式。
4. TUI：`ApiClient` 所有 fetch URL 加 `/v1` 前缀；每个请求带：
   - `Authorization: Bearer <token>` （已有）
   - `X-Client-Id: lhx-rag-cli`
   - `User-Agent: lhx-rag/<version> (...)`

**收益**：

- HF Space / Cloudflare 类反代上把 `/v1/*` 配成"豁免浏览器拦截"，CLI 立即通。
- Web 没动，无回归风险。
- 为 Phase 2 的 `aud` claim、Phase 3 的 device flow 提前埋好路径。

### Phase 2：客户端身份与 scope（中期）

1. 新表 `oauth_clients`，默认 seed `lhx-rag-cli`、`lhx-rag-web`。
2. JWT 加 `aud` 和 `scope` claim；`BearerClientGuard` 强校验 `aud == X-Client-Id`。
3. `/auth/login` 的 response token 携带客户端绑定（按 X-Client-Id 选 TTL/scope）。
4. Web 加 `/me/sessions` 视图，能列出 + 撤销自己的设备。

### Phase 3：Device Authorization Grant（长期）

1. `/oauth/device/authorize` + `/oauth/token` (`grant_type=urn:ietf:params:oauth:grant-type:device_code`)。
2. Web 加 `/device` 确认页（输入 user_code → confirm scope → 完成）。
3. CLI 登录命令重做：`/login` 改为弹 verification_uri + user_code，**不再问 email/password**。
4. keychain 适配（macOS / Windows / Linux）。

### Phase 4+（可选）

- DPoP token binding（RFC 9449）。
- mTLS 用于 `/internal/*`（worker、cron）。
- 风险检测（不寻常地理位置触发 step-up auth）。

## 5. 巧思与权衡总结

| 巧思 | 收益 |
|---|---|
| **路径前缀分离 `/v1/*` vs `/`** | 反代/CDN/WAF 规则可按路径配置，CLI 不再被"非浏览器拦截"误伤 |
| **`OAuthClient` 表 + `aud` claim** | 一套基础设施支撑 CLI/Web/未来 mobile/三方，不重写鉴权 |
| **Device Authorization Grant** | CLI 永远拿不到密码；登录在浏览器完成，UX 也最熟悉 |
| **scope 粒度而不是粗 user role** | token 泄漏的爆炸半径可控 |
| **device_id 绑定 + web 撤销面板** | 用户感知掌控感，符合主流 IDE / AI CLI 规范 |
| **`refresh_token_ttl` 客户端化** | CLI 30 天免登录，Web 7 天，差异化体验 |
| **`X-Client-Id` 必填** | 即使 token 被偷，攻击者用错 client_id 也被拒 |

## 6. 测试矩阵（Phase 1）

| 用例 | 期望 |
|---|---|
| TUI 调 `GET /v1/me`，带 X-Client-Id + Bearer | 200 |
| TUI 调 `GET /v1/me`，缺 X-Client-Id | 400 missing client id |
| TUI 调 `GET /v1/me`，X-Client-Id=`unknown-app` | 400 unknown client |
| Web 调 `GET /me`（无 X-Client-Id，原路径） | 200，行为不变 |
| Web 调 `GET /v1/me` 也通过（带 X-Client-Id=`lhx-rag-web`） | 200，提供平滑迁移路径 |
| OPTIONS 预检 `/v1/...` 任意 Origin | 通过（宽松 CORS） |
| OPTIONS 预检 `/auth/login` 来自非白名单 Origin | 拒绝（保持原行为） |

## 7. 一句话回答

> **能否给后端和 TUI 加一层单独的认证体系？**

**强烈建议——但不是"再加一层"，而是把现有的"一套"拆成"分客户端的协议族"**：同一个用户身份模型 + 多套客户端凭证 + 多套作用域 + 多个 grant flow。这是 OAuth 已经替整个行业回答过的问题，不要重新发明轮子。Phase 1（路径前缀 + `X-Client-Id`）今天就能合，立即解决反代拦截问题；Phase 2/3 让 CLI 与 Web 长期分别演进互不污染。
