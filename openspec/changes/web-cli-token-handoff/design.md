# Design: Web ↔ CLI Token Handoff

## Context

两条独立但互补的路径：

1. **直接复制路径**（最简单，无服务端状态）：
   - Web 把 `{access, refresh}` 编码为 **紧凑字符串**，用户复制，粘贴到 CLI。
   - 适合个人单设备；缺点：明文 token 过剪贴板，有泄漏风险（但用户自己可控）。

2. **user_code 路径**（推荐，服务端状态，类 Device Flow）：
   - Web 请求 `/auth/device-token`，服务端基于当前用户签发一个 `(device_code, user_code)` 对，存 DB 5 分钟。
   - Web 只在 UI 上显示 `user_code`（8 位）。
   - CLI 输入 `user_code` → `/auth/device-token:exchange` → 若未过期/未消费，返回新 TokenPair，标记已消费。
   - 相比路径 1，明文 token 不过用户侧传输，安全更强。

本设计**同时提供两条路径**，用户自选。

## Goals / Non-Goals

**Goals**
- 紧凑字符串编码稳定、带版本号（以便将来升级格式）。
- user_code：高冲突抵抗（Base32 大写，去除易混字符 0/O、1/I），有效期 5 分钟，仅一次性消费。
- CLI 与 Web 行为一致：handoff 后 `/whoami` 显示正确邮箱。

**Non-Goals**
- 不实现 RFC 8628 轮询机制（CLI 主动输入即可，不需 polling device_code）。

## Architecture

### 紧凑字符串格式

```
v1.<base64url(json({a: access, r: refresh, exp: epoch_sec}))>
```

- `v1` 版本前缀，以便 `v2` 未来兼容。
- `exp` 写 access expiry，供 CLI 预检是否过期。
- Web TokenExport：
  ```ts
  const payload = { a: access, r: refresh, exp: Math.floor(accessExp.getTime()/1000) };
  const str = `v1.${btoaUrl(JSON.stringify(payload))}`;
  navigator.clipboard.writeText(str);
  ```

### Device code flow

#### DB 模型

```python
# db/models/device_code.py
class DeviceCode(UUIDMixin, Base):
    __tablename__ = "device_codes"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    device_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # 随机
    user_code: Mapped[str] = mapped_column(String(8), unique=True, index=True)     # 显示
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    consumed_at: Mapped[datetime | None]
```

- `user_code` 字符集：`ABCDEFGHJKLMNPQRSTUVWXYZ23456789`（去 I/O/0/1），`secrets.choice` 抽 8 位。
- 冲突时重试 5 次；仍冲突抛 500。

#### Endpoints

```
POST /auth/device-token
  auth: 已登录（Bearer）
  body: (empty)
  resp: { device_code, user_code, expires_in: 300 }

POST /auth/device-token:exchange
  auth: 未登录（或任意）
  body: { user_code: "AB34EFGH" }
  resp: TokenPair   （同 /auth/login）
  errors:
    404 USER_CODE_NOT_FOUND
    410 USER_CODE_EXPIRED_OR_CONSUMED
```

`AuthService` 增加：

```python
async def create_device_code(self, user_id: UUID) -> tuple[str, str, int]:
    # returns (device_code, user_code, expires_in_seconds)

async def exchange_device_code(self, user_code: str) -> TokenPair:
    # 原子：SELECT FOR UPDATE ... 检查 expires_at > now() AND consumed_at IS NULL
    # 标记 consumed_at = now()
    # 为该 user 签发新的 access + refresh（走和 login 一样的签发逻辑）
```

### CLI 斜杠命令

```python
# app/chat_app.py
async def cmd_login_with_token(ctx, arg_line):
    s = arg_line.strip() or await ctx.view.prompt("paste token: ")
    pair = parse_compact_token(s)
    user = await auth_service.get_user_by_access(pair.access_token)
    auth_local.save(pair)
    view.system_notice(f"logged in as {user.email}")

async def cmd_login_with_code(ctx, arg_line):
    code = (arg_line or await ctx.view.prompt("user code: ")).strip().upper()
    pair = await auth_service.exchange_device_code(code)
    auth_local.save(pair)
    view.system_notice("logged in via device code")

async def cmd_token_export(ctx, _):
    pair = auth_local.load()
    if not pair: view.error("NO_TOKEN", "not logged in"); return
    s = build_compact_token(pair)
    view.system_notice("token copied; or scan QR:")
    print_terminal_qr(s)       # qrcode 包生成 ASCII QR
```

### Web 侧

`TokenExport.tsx`（放 header avatar 下拉）：

```tsx
function TokenExport() {
  const { access, refresh } = useAuth();
  async function copy() {
    if (!access || !refresh) return;
    const exp = jwtDecode<{exp:number}>(access).exp;
    const s = `v1.${b64url(JSON.stringify({ a: access, r: refresh, exp }))}`;
    await navigator.clipboard.writeText(s);
    toast.success("copied");
  }
  async function genCode() {
    const { user_code, expires_in } = await api("/auth/device-token", { method: "POST" });
    setShowDialog({ user_code, expires_in });
  }
  return <Dropdown>…</Dropdown>;
}
```

Dialog 显示：
```
user code:  AB34EFGH
 expires in:  4:55
```

倒计时到 0 自动关闭。

### Router & route guard

- `/login-with-token`：用 placeholder 前用 `ProtectedRoute=false`；表单提交成功后跳 `/chat`。

## Alternatives Considered

- **实现完整 OAuth2 Device Flow**：服务端不再需要登录态，CLI 可不需要邮箱密码也能登录（从其他渠道拿 auth code）。过重，本期不做。
- **直接扫描二维码自动登录**：需要设备摄像头 + 二维码扫描库，桌面 CLI 场景价值有限；二维码只作为"换设备"的便捷显示。

## Risks & Mitigations

- **风险**：紧凑 token 字符串在剪贴板 / 浏览器历史中泄漏。
  **缓解**：UI 明显提示"仅本机使用；贴完请清空剪贴板"；Web 侧"复制"按钮 10 秒后清剪贴板（可选）。
- **风险**：`user_code` 被暴力枚举。
  **缓解**：8 位字母数字 = 32^8 ≈ 1.1e12 空间；5 分钟内每 IP 限 10 次尝试（走 Change 8 的 rate limit）。
- **风险**：`exchange_device_code` 并发竞态。
  **缓解**：SQL 用 `UPDATE ... SET consumed_at=now() WHERE consumed_at IS NULL AND expires_at > now() AND user_code=:c RETURNING user_id`，只有 RETURNING 非空才成功。
- **风险**：CLI 保存的 token 文件权限错误。
  **缓解**：Change 5 已定义 0600 存储；本 change 不变更。

## Testing Strategy

- 单元：
  - `tests/unit/core/auth/test_device_code.py`：create → exchange 正常；过期 → 410；已消费 → 410；重复 exchange 失败。
  - `tests/unit/app/test_compact_token.py`：`build_compact_token / parse_compact_token` round-trip；版本号错误 → `ValueError`。
- 集成：
  - `tests/api/test_device_code_flow.py`：完整 Web+CLI 流程（httpx 模拟两端）。
- 手动：
  - 浏览器复制 → 终端 `/login-with-token` 粘贴 → `/whoami` 正确。
  - 浏览器生成 user_code → 终端 `/login-with-code` → `/whoami` 正确。
