# Tasks: Web ↔ CLI Token Handoff

## 1. 依赖

- [ ] 1.1 Python：`pyproject.toml` 新增 `qrcode[pil]>=7.4`（CLI 打印二维码需要）。
- [ ] 1.2 Web：`pnpm add qrcode.react jwt-decode`。
- [ ] 1.3 `uv sync` + `pnpm install` 成功。

## 2. DB 模型 + 迁移

- [ ] 2.1 `db/models/device_code.py`：`DeviceCode` 表。
- [ ] 2.2 `db/models/__init__.py` re-export。
- [ ] 2.3 `alembic revision -m "add device_codes table" --autogenerate`。
- [ ] 2.4 迁移文件补索引（`user_code` unique + `expires_at` index）。
- [ ] 2.5 `alembic upgrade head` 成功。

## 3. 紧凑 token 编解码

- [ ] 3.1 `app/compact_token.py`：`build_compact_token(pair) -> str`、`parse_compact_token(s) -> TokenPair`。
- [ ] 3.2 版本前缀 `v1.`；base64url 无 padding。
- [ ] 3.3 错误处理：非 v1 前缀 → `UnsupportedVersion`；JSON 失败 → `MalformedToken`；字段缺失 → `MalformedToken`。
- [ ] 3.4 单测：round-trip + 各错误路径。
- [ ] 3.5 Web 对应函数 `web/src/lib/compactToken.ts`（与 Python 行为对齐）。

## 4. core auth service 扩展

- [ ] 4.1 `core/auth/service.py` 新增：
  - `create_device_code(user_id) -> DeviceCodeOut`。
  - `exchange_device_code(user_code) -> TokenPair`。
- [ ] 4.2 `user_code` 生成：`secrets.choice` + 32-char alphabet（去 IO01），8 位，冲突重试 5 次。
- [ ] 4.3 `exchange` 使用 SQL `UPDATE ... RETURNING`（见 design 原子消费）。
- [ ] 4.4 过期 / 已消费 / 未找到 → 抛 `DeviceCodeExpiredError` / `DeviceCodeConsumedError` / `DeviceCodeNotFoundError`（继承 `AuthError`）。
- [ ] 4.5 新增到 `core/auth/errors.py`。

## 5. API 端点

- [ ] 5.1 `api/routers/auth.py` 新增 `POST /auth/device-token`：需登录，调 `create_device_code`。
- [ ] 5.2 新增 `POST /auth/device-token:exchange`：不需登录，body `{user_code}`，调 `exchange_device_code`。
- [ ] 5.3 `api/middleware/errors.py` 映射：
  - `DeviceCodeExpiredError`/`DeviceCodeConsumedError` → 410 `USER_CODE_EXPIRED_OR_CONSUMED`。
  - `DeviceCodeNotFoundError` → 404 `USER_CODE_NOT_FOUND`。
- [ ] 5.4 Rate limit 规则加入 `POST /auth/device-token:exchange` 10/min/ip（Change 8 的 rules 扩展）。
- [ ] 5.5 schema：`api/schemas/auth.py` 新增 `DeviceCodeOut(device_code, user_code, expires_in)` + `DeviceCodeExchangeIn(user_code)`。

## 6. CLI 斜杠命令

- [ ] 6.1 `app/chat_app.py` 注册：`/login-with-token`、`/login-with-code`、`/token-export`。
- [ ] 6.2 `/login-with-token`：交互粘贴 → 解析 → 校验 `/me` → `auth_local.save`。
- [ ] 6.3 `/login-with-code`：交互输入 8 位 → `exchange` → `auth_local.save`。
- [ ] 6.4 `/token-export`：读 token.json → 编 compact string → 复制到剪贴板（用 `pyperclip` 或打印+提示）。
  - 无 `pyperclip` 依赖：默认打印字符串；若 `pyperclip` 安装（可选 dev dep）则 copy。
  - 同时打印 ASCII QR：`qrcode.QRCode` → `print_ascii` API。
- [ ] 6.5 帮助文本：`/help` 展示三个新命令简介。

## 7. Web 端

### 7.1 `features/auth/TokenExport.tsx`
- [ ] 7.1.1 放在 header avatar 下拉菜单里。
- [ ] 7.1.2 "复制 token" 按钮：编码 + `navigator.clipboard.writeText`；10s 后 toast 提示"剪贴板已清除"并 `writeText("")`。
- [ ] 7.1.3 "生成登录码" 按钮：调 `/auth/device-token`，打开 Dialog。

### 7.2 Dialog（一次性组件）
- [ ] 7.2.1 显示 `user_code` + 大号字体，可复制。
- [ ] 7.2.2 `qrcode.react` 渲染二维码（值 = 紧凑 token 字符串，方便"同机换端"；user_code 则单纯文本，不压入 QR）。
- [ ] 7.2.3 倒计时从 300s；到 0 关闭并 toast"已过期"。

### 7.3 `features/auth/LoginWithToken.tsx`
- [ ] 7.3.1 路由 `/login-with-token`：Textarea + 登录按钮。
- [ ] 7.3.2 提交：解析紧凑字符串 → 写 zustand → `navigate("/chat")`。
- [ ] 7.3.3 失败显示明确错误（版本/格式/过期）。

### 7.4 `features/auth/LoginWithCode.tsx`
- [ ] 7.4.1 路由 `/login-with-code`：8 位格式化输入（`<input>` + 正则限制 A-Z/2-9）。
- [ ] 7.4.2 提交：`POST /auth/device-token:exchange` → 写 zustand → 跳 `/chat`。

### 7.5 路由注册
- [ ] 7.5.1 `router.tsx` 加 `/login-with-token` `/login-with-code`，均为 Public。

## 8. 测试

- [ ] 8.1 `tests/unit/core/auth/test_device_code.py`：
  - 创建 → exchange 成功；再次 exchange → `DeviceCodeConsumedError`。
  - 过期（手动把 `expires_at` 设过去）→ 410。
- [ ] 8.2 `tests/unit/app/test_compact_token.py`：round-trip + 错误路径。
- [ ] 8.3 `tests/api/test_device_flow.py`：完整 HTTP 流程。
- [ ] 8.4 Web `src/__tests__/compactToken.test.ts`：与 Python 对齐的 round-trip。
- [ ] 8.5 `uv run pytest -q -k device_code` 绿；`pnpm test` 绿。

## 9. 文档

- [ ] 9.1 `docs/USER_GUIDE.md` 新增"跨端登录"章节：两条路径图示。
- [ ] 9.2 AGENTS.md §19 追加 "web-cli token handoff"。

## 10. 冒烟

- [ ] 10.1 Web 登录 → 复制 token → 终端 `/login-with-token` 粘贴 → `/whoami` 显示邮箱。
- [ ] 10.2 Web 生成 8 位 code → 终端 `/login-with-code` → `/whoami`。
- [ ] 10.3 第二次用同一 code 失败 410。
- [ ] 10.4 5 分钟后 code 自动失效。
- [ ] 10.5 CLI `/token-export` 打印出 v1.xxxxx 且 ASCII QR 正确（可用手机扫描识别字符串，或命令行 `qrencode -d` 反解）。
