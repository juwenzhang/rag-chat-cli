# Proposal: Web ↔ CLI Token Handoff

## Why

AGENTS.md §9 / §15 P9 提出一个关键体验：

> 用户在 Web 登录后，一键生成 token 字符串 / 扫码 / 复制，粘贴到 CLI 直接登录，不需要再输入邮箱密码。
> 反之，CLI 已登录时可以导出 token 供 Web 使用（开发调试）。

这是"同一套鉴权、跨端无缝"的体现，也是 RAG 项目差异化体验点之一。前置 Change 5/13 把 auth 双端分别做好，本次把它们粘合。

## What Changes

### Web 端
- `features/auth/TokenExport.tsx`（在 `/settings/tokens` 或 header 下拉里）：
  - 按钮 "复制为 CLI token"：将当前 `access + refresh` 编码为 **紧凑字符串**（base64-url JSON）后 copy。
  - 按钮 "生成二维码"：用 `qrcode.react` 渲染同一字符串（CLI 可用 `pyzbar` 识别；非目标）。
  - 按钮 "撤销当前 refresh" —— 调用 `/auth/logout`。
- `features/auth/LoginWithToken.tsx`（`/login-with-token` 路由）：
  - 粘贴框 + "登录" 按钮，解析 token 字符串 → 调 `GET /me` 校验 → 写入 zustand + 跳 `/chat`。

### API 端
- `api/routers/auth.py` 新增 `POST /auth/device-token`：
  - 已登录 → 服务端签发一个**短期（5 分钟）的 device_code**，返回 `{device_code, user_code}`；
  - `user_code` 是 8 位大写字母数字，显示给用户，让他在**另一端**输入。
- `api/routers/auth.py` 新增 `POST /auth/device-token:exchange`：
  - 未登录 CLI 输入 `user_code` → 服务端查 device_code → 返回正常 `TokenPair`。
  - device_code 仅一次性、5 分钟、失败后撤销。

### CLI 端
- 新增斜杠命令 `/login-with-token`：
  - 弹出输入框让用户粘贴从 Web 复制的紧凑 token 字符串；
  - 解析 → 调 `/me` → 保存到 `~/.config/rag-chat/token.json`。
- 新增斜杠命令 `/login-with-code`：
  - 输入 Web 显示的 8 位 user_code → 调 `/auth/device-token:exchange` → 拿到 token → 保存。
- 新增 `/token-export`：把本地 `token.json` 编为紧凑字符串 + 二维码（ASCII QR）打印到 TTY（复用 `qrcode` Python 包）。

### 依赖
- Web 新增：`qrcode.react@3`。
- Python 新增：`qrcode[pil]>=7.4`（生成 ASCII / terminal QR）。

## Non-goals

- 不做浏览器插件 / 原生 messaging。
- 不做短链 / `rag://` protocol handler 注册。
- 不做 SSO。
- 不做真正的 OAuth2 Device Flow（我们是简化版：user_code 5 分钟，不是标准 RFC 8628）。

## Impact

- **新增**：`features/auth/TokenExport.tsx`、`features/auth/LoginWithToken.tsx`、Web 路由注册；`api/routers/auth.py` 两个 endpoint；CLI 3 个斜杠命令；`db/models/device_code.py` + alembic migration。
- **修改**：`core/auth/service.py` 新增 `create_device_code / exchange_device_code`；`app/chat_app.py` 斜杠命令注册。
- **依赖**：`qrcode.react`（web）、`qrcode[pil]`（py）。
- **风险**：低-中。多一张小表 + 两个端点；必须 5 分钟内一次性消费的语义严谨。
- **回退方式**：`git revert` 本 change；db migration downgrade。
