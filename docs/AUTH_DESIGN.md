# 认证体系升级设计（v2.x）

> 当前 v1.x 仅使用 JWT body 返回的方案存在 XSS 风险、缺少防机器人。
> 本文设计 v2.x 的多重防护方案：**JWT + HttpOnly Cookie + 邮箱验证码**。
>
> 对应路线图：[ROADMAP.md](./ROADMAP.md) Phase 1。

---

## 1. 现状回顾

```http
POST /auth/login
Body: {"email": "...", "password": "..."}
Response 200:
{
  "access_token": "eyJ...",     ← 暴露在 JS / response body
  "refresh_token": "eyJ...",    ← 客户端自己存
  "access_expires_at": "...",
  "refresh_expires_at": "..."
}
```

**风险：**
1. `access_token` 在 JS 中暴露 → XSS 漏洞可窃取
2. 无图形/邮箱验证码 → 暴力破解、机器人注册
3. 客户端需自己存 token → localStorage 不安全，sessionStorage 不能跨标签页
4. CSRF 防护需要应用层自行实现

---

## 2. 升级方案

### 2.1 总体策略

```
┌─────────────────────────────────────────────────────────┐
│  Browser                                                │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Cookies (HttpOnly, Secure, SameSite=Lax)          │  │
│  │   - access_token       (15min)                    │  │
│  │   - refresh_token      (7day, path=/auth/refresh) │  │
│  │   - csrf_token         (与 access 同生命周期)      │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                │   每次请求自动携带 Cookie
                │   + JS 读取 csrf_token 放到 Header
                ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI                                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │ 鉴权中间件：                                       │   │
│  │  1. 读 Cookie 中的 access_token                   │   │
│  │  2. 校验 CSRF Header == Cookie 中的 csrf_token   │   │
│  │  3. 注入 current_user                            │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Cookie 设计

| Cookie | HttpOnly | Secure | SameSite | Path | TTL | 内容 |
|--------|----------|--------|----------|------|-----|------|
| `access_token` | ✅ | ✅(prod) | Lax | `/` | 15min | JWT |
| `refresh_token` | ✅ | ✅(prod) | Strict | `/auth/refresh` | 7day | JWT |
| `csrf_token` | ❌ | ✅(prod) | Lax | `/` | 15min | 随机 base64 |

> `csrf_token` 必须 JS 可读（不是 HttpOnly），因为前端要把它放进请求头。  
> 但攻击者要伪造请求，需要同时拿到 Cookie（同源限制）+ Header（CSRF token）→ 双重防护。

### 2.3 验证码流程

```
注册 / 重置密码 / 异常登录时启用：

  1. 前端：用户填邮箱 → POST /auth/code/send {email, purpose}
                       ↓
  2. 后端：生成 6 位数字（Redis: code:{email}:{purpose}, TTL=10min）
                       发送邮件 (SMTP)
                       返回 {sent: true, expires_in: 600}
                       ↓
  3. 前端：用户填验证码 → POST /auth/register {email, password, code}
                       ↓
  4. 后端：校验 Redis 中的 code，匹配后删除，继续注册流程
```

**安全控制：**
- 同一邮箱 60 秒内只能发一次（防滥用）
- 同 IP 每小时最多 5 次（IP rate limit）
- 验证码错误 5 次后失效（暴力破解防护）
- 验证码与 purpose 绑定（不能注册时拿到的 code 用于登录）

### 2.4 登录流程详解

```http
# Step 1: 用户提交邮箱+密码
POST /auth/login
Content-Type: application/json
{"email": "u@example.com", "password": "..."}

# Step 2: 后端验证后 Set-Cookie
HTTP/1.1 200 OK
Set-Cookie: access_token=eyJ...; HttpOnly; Secure; SameSite=Lax; Max-Age=900; Path=/
Set-Cookie: refresh_token=eyJ...; HttpOnly; Secure; SameSite=Strict; Max-Age=604800; Path=/auth/refresh
Set-Cookie: csrf_token=abc123...; Secure; SameSite=Lax; Max-Age=900; Path=/
Content-Type: application/json
{
  "user": {"id": "...", "email": "...", "display_name": "..."}
}

# Step 3: 后续请求
GET /me
Cookie: access_token=eyJ...; csrf_token=abc123...
X-CSRF-Token: abc123...        ← 前端 JS 读 cookie 后回填
```

### 2.5 刷新流程

```http
POST /auth/refresh
Cookie: refresh_token=eyJ...
X-CSRF-Token: abc123...

Response:
Set-Cookie: access_token=eyJ_new...
Set-Cookie: csrf_token=new_random
Set-Cookie: refresh_token=eyJ_new...   ← 轮换
```

> 刷新失败（reuse detected / expired）→ 全部 Cookie 清空，前端跳转登录页。

### 2.6 登出流程

```http
POST /auth/logout
Cookie: access_token, refresh_token, csrf_token

Response:
HTTP/1.1 204
Set-Cookie: access_token=; Max-Age=0
Set-Cookie: refresh_token=; Max-Age=0
Set-Cookie: csrf_token=; Max-Age=0
（后端同时 revoke refresh_token 的 jti）
```

---

## 3. 后端实施清单

### 3.1 新增端点

```python
POST /auth/code/send   # 发送邮箱验证码
   body: {"email": str, "purpose": "register"|"reset"|"login_2fa"}
   response: {"sent": true, "expires_in": 600}

POST /auth/register    # （现有，参数增加 code）
   body: {"email", "password", "display_name", "code"}

POST /auth/login       # （现有，行为变化：返回 Cookie 而非 body token）

POST /auth/refresh     # （现有，行为变化：读 Cookie，写 Cookie）

POST /auth/logout      # （现有，行为变化：清 Cookie）

GET /auth/csrf         # 前端首次访问时获取 csrf token
   response: {"csrf_token": "..."}
```

### 3.2 新增依赖

```toml
[project]
dependencies = [
    # ...
    "aiosmtplib>=3.0",   # 异步 SMTP
    "itsdangerous>=2.1",  # CSRF token 签名
]
```

或者直接用 Redis 存随机 token，不签名。

### 3.3 新增配置（`.env`）

```bash
# SMTP（邮箱验证码）
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=noreply@example.com
SMTP_PASSWORD=...
SMTP_FROM_NAME=lhx-rag
SMTP_TLS=true

# Cookie 配置
COOKIE_DOMAIN=             # 空 = 当前域；跨子域写 .example.com
COOKIE_SECURE=true         # prod 必须 true，dev 可为 false
COOKIE_SAMESITE=lax        # lax | strict | none

# 验证码
VERIFY_CODE_TTL_SEC=600
VERIFY_CODE_RESEND_INTERVAL_SEC=60
VERIFY_CODE_MAX_ATTEMPTS=5
VERIFY_CODE_IP_HOURLY_LIMIT=5
```

### 3.4 改造点

| 文件 | 改动 |
|------|------|
| `api/routers/auth.py` | 加 `/code/send`、`/csrf`；login/logout/refresh 用 Cookie |
| `api/deps.py` | 新增 `get_current_user_from_cookie` 替换 `get_current_user` |
| `api/middleware/csrf.py` | 新增 CSRF 校验中间件 |
| `core/auth/service.py` | 加 `send_verification_code` / `verify_code` |
| `core/auth/code.py` | 新增 Redis 验证码存取 |
| `core/email/smtp.py` | 新增 SMTP 客户端封装 |
| `db/models.py` | （可选）verify_code_attempts 表，或纯 Redis |

### 3.5 兼容性

旧客户端（CLI v1.x、第三方按 Bearer 调用）继续支持：
- `Authorization: Bearer <token>` Header 仍有效
- 同时支持 Cookie 和 Bearer，鉴权中间件按优先级取 token
- 这样 CLI 不必立即升级

---

## 4. 前端实施清单（Next.js）

### 4.1 API 客户端

```typescript
// websites/src/lib/api.ts
const api = {
  async post(path: string, body?: unknown) {
    const csrf = getCookie('csrf_token');
    return fetch(`${API_BASE}${path}`, {
      method: 'POST',
      credentials: 'include',            // 关键：带 Cookie
      headers: {
        'Content-Type': 'application/json',
        ...(csrf ? {'X-CSRF-Token': csrf} : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  },
  // ...
};
```

### 4.2 页面流程

```
/register
  ├─ 填邮箱 → 点"发送验证码" → POST /auth/code/send
  ├─ 收到邮件 → 填验证码 + 密码 → POST /auth/register
  └─ 注册成功 → 自动登录 → 跳 /

/login
  ├─ 填邮箱 + 密码 → POST /auth/login
  ├─ 后端 Set-Cookie → 浏览器自动保存
  └─ 跳 /

异常情况：
- 同 IP 短时多次失败登录 → 触发验证码 (purpose=login_2fa)
- 异地登录 → 邮箱通知
```

### 4.3 状态管理

- 不用 Redux/Zustand 存 token（Cookie 是真相源）
- `/me` 端点用 SWR / React Query 拉用户信息
- 401 响应 → 自动尝试 `/auth/refresh`，失败再跳登录页

---

## 5. 安全总结

| 攻击 | 防御 |
|------|------|
| XSS 窃取 token | HttpOnly Cookie，JS 无法读取 |
| CSRF | SameSite=Lax + CSRF token Header 双重 |
| 暴力破解密码 | 邮箱 + 同 IP 限流 + 验证码触发 |
| 机器人注册 | 邮箱验证码 (purpose=register) |
| 刷新 token 泄漏 | path=`/auth/refresh` 限制 + rotation + reuse detect |
| 会话固定 | login 时重新生成 csrf_token |
| MITM | Secure flag（prod 强制 HTTPS） |

---

## 6. 实施顺序

1. ✅ 设计文档（本文）
2. ⏳ 后端：`/auth/code/send` + Redis 存验证码 + SMTP
3. ⏳ 后端：login/refresh/logout 改为 Cookie + CSRF
4. ⏳ 前端：register / login 页面
5. ⏳ 前端：API 客户端封装（自动带 Cookie + CSRF + 401 重试）
6. ⏳ 测试：单元 + 集成 + e2e

## 7. 测试策略

- 单元测试：`AuthService.send_code`, `verify_code`, rate limit
- 集成测试：完整 register → email mock → verify → login → access → refresh 流程
- e2e（Playwright）：浏览器走完整流程，确认 Cookie 行为正确
